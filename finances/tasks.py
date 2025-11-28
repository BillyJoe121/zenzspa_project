"""
Tareas de Celery para el módulo finances.

Incluye tasks de:
- Pagos pendientes
- Suscripciones VIP recurrentes
- Expiración de suscripciones VIP
- Comisiones del desarrollador
"""
import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.models import GlobalSettings, AuditLog
from users.models import CustomUser
from notifications.services import NotificationService
from .services import DeveloperCommissionService
from .payments import PaymentService
from .models import Payment

logger = logging.getLogger(__name__)


@shared_task
def run_developer_payout():
    """
    Task periódica para evaluar y ejecutar el payout al desarrollador
    en función de la deuda y el saldo Wompi disponible.
    """
    return DeveloperCommissionService.evaluate_payout()


@shared_task
def check_pending_payments():
    """
    Verifica pagos pendientes que podrían haberse quedado sin webhook.
    Migrado desde spa.tasks para centralizar lógica de pagos.
    """
    threshold = timezone.now() - timedelta(minutes=10)
    pending_payments = Payment.objects.filter(
        status=Payment.PaymentStatus.PENDING,
        created_at__lt=threshold,
    )[:100]
    reviewed = 0
    for payment in pending_payments:
        PaymentService.poll_pending_payment(payment)
        reviewed += 1
    return f"Pagos pendientes revisados: {reviewed}"


@shared_task
def process_recurring_subscriptions():
    """
    Intenta cobrar y extender suscripciones VIP que están por vencer.
    Migrado desde spa.tasks para centralizar lógica de suscripciones VIP.
    """
    settings_obj = GlobalSettings.load()
    vip_price = settings_obj.vip_monthly_price
    if vip_price is None or vip_price <= 0:
        return "Precio VIP no configurado."

    today = timezone.now().date()
    window = today + timedelta(days=3)
    users = CustomUser.objects.filter(
        role=CustomUser.Role.VIP,
        vip_auto_renew=True,
        vip_expires_at__isnull=False,
        vip_expires_at__lte=window,
    )

    processed = 0
    for user in users:
        reference = f"VIP-AUTO-{user.id}-{uuid.uuid4().hex[:8]}"
        transaction_payload = {"reference": reference, "status": "PENDING"}
        status_result = Payment.PaymentStatus.DECLINED

        if user.vip_payment_token:
            try:
                status_result, transaction_payload, reference = PaymentService.charge_recurrence_token(
                    user=user,
                    amount=vip_price,
                    token=user.vip_payment_token,
                )
            except Exception as exc:
                logger.exception(
                    "Error al ejecutar el cobro recurrente VIP para el usuario %s",
                    user.id,
                )
                transaction_payload = {
                    "reference": reference,
                    "status": "ERROR",
                    "error": str(exc),
                }
                status_result = Payment.PaymentStatus.DECLINED
        else:
            logger.warning(
                "Usuario %s no tiene token de pago VIP; el cobro se marcará como fallido.",
                user.id,
            )
            transaction_payload = {
                "reference": reference,
                "status": "ERROR",
                "error": "missing_token",
            }

        payment = Payment.objects.create(
            user=user,
            amount=vip_price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.VIP_SUBSCRIPTION,
            transaction_id=reference,
        )

        final_status = PaymentService.apply_gateway_status(
            payment, status_result, transaction_payload)

        if final_status == Payment.PaymentStatus.APPROVED:
            user.vip_failed_payments = 0
            user.save(update_fields=['vip_failed_payments', 'updated_at'])
            processed += 1
            continue

        if final_status == Payment.PaymentStatus.PENDING:
            logger.info(
                "Cobro VIP recurrente pendiente para el usuario %s; esperando confirmación de Wompi.",
                user.id,
            )
            # No alteramos los contadores hasta recibir webhook/consulta.
            continue

        user.vip_failed_payments += 1
        subscription_status = "PAST_DUE"
        if user.vip_failed_payments >= 3:
            user.vip_auto_renew = False
            subscription_status = "CANCELLED"
        user.save(update_fields=['vip_failed_payments',
                  'vip_auto_renew', 'updated_at'])
        try:
            NotificationService.send_notification(
                user=user,
                event_code="VIP_RENEWAL_FAILED",
                context={
                    "failed_attempts": user.vip_failed_payments,
                    "status": subscription_status,
                },
            )
        except Exception:
            logger.exception(
                "No se pudo notificar fallo de renovación VIP para el usuario %s", user.id)
    return f"Renovaciones intentadas: {processed}"


@shared_task
def downgrade_expired_vips():
    """
    Degrada usuarios VIP cuyo período expiró.
    Migrado desde spa.tasks para centralizar lógica de suscripciones VIP.
    """
    today = timezone.now().date()
    expired_users = CustomUser.objects.filter(
        role=CustomUser.Role.VIP,
        vip_expires_at__isnull=False,
        vip_expires_at__lt=today,
    )
    count = 0
    for user in expired_users:
        expired_at = user.vip_expires_at
        user.role = CustomUser.Role.CLIENT
        user.vip_auto_renew = False
        user.vip_active_since = None
        user.vip_failed_payments = 0
        user.save(update_fields=['role', 'vip_auto_renew',
                  'vip_active_since', 'vip_failed_payments', 'updated_at'])
        AuditLog.objects.create(
            admin_user=None,
            target_user=user,
            action=AuditLog.Action.VIP_DOWNGRADED,
            details=f"Usuario {user.id} degradado a CLIENT por expiración VIP.",
        )
        try:
            NotificationService.send_notification(
                user=user,
                event_code="VIP_MEMBERSHIP_EXPIRED",
                context={
                    "expired_at": expired_at.isoformat() if expired_at else None,
                },
            )
        except Exception:
            logger.exception(
                "No se pudo notificar expiración VIP para el usuario %s", user.id)
        count += 1
    return f"Usuarios degradados: {count}"
