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
from .models import Payment, WebhookEvent

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
    updated = 0
    for payment in pending_payments:
        before = payment.status
        result = PaymentService.poll_pending_payment(payment)
        if result and payment.status != before:
            updated += 1
        reviewed += 1
    return f"Pagos pendientes revisados: {reviewed}, actualizados: {updated}"


@shared_task
def reconcile_recent_payments(hours=24, limit=200):
    """
    Reconciliación ligera: consulta Wompi para pagos recientes no aprobados
    y corrige estado si difiere.
    """
    cutoff = timezone.now() - timedelta(hours=hours)
    candidates = (
        Payment.objects.filter(
            transaction_id__isnull=False,
            transaction_id__gt="",
            created_at__gte=cutoff,
            status__in=[
                Payment.PaymentStatus.PENDING,
                Payment.PaymentStatus.DECLINED,
                Payment.PaymentStatus.ERROR,
                Payment.PaymentStatus.TIMEOUT,
            ],
        )
        .order_by("-created_at")[:limit]
    )
    checked = 0
    updated = 0
    for payment in candidates:
        checked += 1
        if PaymentService.poll_pending_payment(payment):
            payment.refresh_from_db()
            if payment.status in (
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.DECLINED,
                Payment.PaymentStatus.ERROR,
                Payment.PaymentStatus.TIMEOUT,
            ):
                updated += 1
    return f"Reconciliación: revisados={checked}, actualizados={updated}"


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
            user_name = user.get_full_name() or user.first_name or "Cliente"
            NotificationService.send_notification(
                user=user,
                event_code="VIP_RENEWAL_FAILED",
                context={
                    "user_name": user_name,
                    "status": subscription_status,
                    "failed_attempts": user.vip_failed_payments,
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
            user_name = user.get_full_name() or user.first_name or "Cliente"
            NotificationService.send_notification(
                user=user,
                event_code="VIP_MEMBERSHIP_EXPIRED",
                context={
                    "user_name": user_name,
                    "expired_at": expired_at.isoformat() if expired_at else None,
                },
            )
        except Exception:
            logger.exception(
                "No se pudo notificar expiración VIP para el usuario %s", user.id)
        count += 1
    return f"Usuarios degradados: {count}"


@shared_task
def cleanup_old_webhook_events():
    """
    Limpia registros antiguos de WebhookEvent para prevenir crecimiento ilimitado.

    Elimina eventos procesados/ignorados con más de 90 días de antigüedad,
    y eventos fallidos con más de 180 días.

    Se mantienen eventos recientes para auditoría y debugging.
    """
    now = timezone.now()

    # Eliminar eventos procesados/ignorados con más de 90 días
    processed_threshold = now - timedelta(days=90)
    deleted_processed = WebhookEvent.objects.filter(
        status__in=[WebhookEvent.Status.PROCESSED, WebhookEvent.Status.IGNORED],
        created_at__lt=processed_threshold
    ).delete()[0]

    # Eliminar eventos fallidos con más de 180 días (más tiempo para debugging)
    failed_threshold = now - timedelta(days=180)
    deleted_failed = WebhookEvent.objects.filter(
        status=WebhookEvent.Status.FAILED,
        created_at__lt=failed_threshold
    ).delete()[0]

    total_deleted = deleted_processed + deleted_failed

    logger.info(
        f"Cleanup de WebhookEvent: {deleted_processed} procesados/ignorados (>90d), "
        f"{deleted_failed} fallidos (>180d). Total: {total_deleted}"
    )

    return {
        "deleted_processed": deleted_processed,
        "deleted_failed": deleted_failed,
        "total_deleted": total_deleted
    }
