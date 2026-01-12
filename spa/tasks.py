import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.models import GlobalSettings, AuditLog
from users.models import CustomUser
from .models import Appointment, WaitlistEntry, LoyaltyRewardLog
from finances.models import Payment, ClientCredit
from finances.payments import PaymentService
from notifications.services import NotificationService

# Se obtiene una instancia del logger.
logger = logging.getLogger(__name__)


@shared_task
def _send_reminder_for_appointment(appointment_id):
    """
    Tarea auxiliar que envía recordatorio de cita por WhatsApp y Email.
    Migrado al sistema centralizado de NotificationService.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        user = appointment.user

        if not user:
            logger.warning("Cita %s no tiene usuario asignado", appointment_id)
            return

        # Preparar información de la cita
        start_time_local = appointment.start_time.astimezone(timezone.get_current_timezone())
        services = appointment.get_service_names()

        # Preparar contexto para NotificationService
        context = {
            "user_name": user.get_full_name() or user.first_name or "Cliente",
            "start_date": start_time_local.strftime("%d de %B %Y"),
            "start_time": start_time_local.strftime("%I:%M %p"),
            "services": services,
            "total": f"{appointment.total:,.0f}" if hasattr(appointment, 'total') and appointment.total else "0",
        }

        # Enviar notificación usando el sistema centralizado
        NotificationService.send_notification(
            user=user,
            event_code="APPOINTMENT_REMINDER_24H",
            context=context,
            priority="high"
        )

        logger.info("Recordatorio de cita %s enviado a %s", appointment_id, user.email or user.phone_number)

    except Appointment.DoesNotExist:
        logger.error("No se encontró la cita %s para enviar recordatorio.", appointment_id)
    except Exception as e:
        logger.error("Error enviando recordatorio de cita %s: %s", appointment_id, e)


@shared_task
def send_appointment_reminder():
    """
    Tarea periódica que programa recordatorios para las citas en las próximas 24 horas.
    """
    now = timezone.now()
    reminder_start_time = now + timedelta(hours=24)
    reminder_end_time = now + timedelta(hours=25)

    appointments = Appointment.objects.filter(
        start_time__range=(reminder_start_time, reminder_end_time),
        status__in=[
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ],
    )
    for appointment in appointments:
        _send_reminder_for_appointment.delay(str(appointment.id))
    logger.info("Se programaron %s recordatorios de citas.",
                appointments.count())





@shared_task
def cancel_unpaid_appointments():
    """
    Cancela citas cuyo anticipo no se ha pagado y notifica la lista de espera.
    """
    from .services import WaitlistService

    settings_obj = GlobalSettings.load()
    expiration_minutes = max(1, settings_obj.advance_expiration_minutes)

    time_threshold = timezone.now() - timedelta(minutes=expiration_minutes)
    unpaid_appointments = Appointment.objects.filter(
        status=Appointment.AppointmentStatus.PENDING_PAYMENT,
        created_at__lt=time_threshold,
    )

    if not unpaid_appointments.exists():
        return "No hay citas pendientes de pago para cancelar."

    cancelled_count = 0
    for appt in unpaid_appointments:
        appt.status = Appointment.AppointmentStatus.CANCELLED
        appt.outcome = Appointment.AppointmentOutcome.CANCELLED_BY_SYSTEM
        appt.save(update_fields=['status', 'outcome', 'updated_at'])
        WaitlistService.offer_slot_for_appointment(appt)
        AuditLog.objects.create(
            admin_user=None,
            target_user=appt.user,
            target_appointment=appt,
            action=AuditLog.Action.SYSTEM_CANCEL,
            details="Cancelación automática por falta de pago.",
        )
        try:
            start_time_local = timezone.localtime(appt.start_time)
            NotificationService.send_notification(
                user=appt.user,
                event_code="APPOINTMENT_CANCELLED_AUTO",
                context={
                    "user_name": (
                        appt.user.get_full_name()
                        or appt.user.first_name
                        or "Cliente"
                    ),
                    "start_date": start_time_local.strftime("%d de %B %Y"),
                    "appointment_id": str(appt.id),
                    "start_time": appt.start_time.isoformat(),
                },
            )
        except Exception:
            logger.exception(
                "Error enviando notificación de cancelación automática para cita %s", appt.id)
        logger.info(
            "Cita %s cancelada por falta de pago; se notificó a la lista de espera.",
            appt.id,
        )
        cancelled_count += 1

    return f"{cancelled_count} citas pendientes de anticipo han sido canceladas."


# MIGRADO A finances.tasks.check_pending_payments
# Esta función se mantiene solo para compatibilidad temporal
@shared_task
def check_pending_payments():
    """
    DEPRECADO: Migrado a finances.tasks.check_pending_payments

    Verifica pagos pendientes que podrían haberse quedado sin webhook.
    """
    from finances.tasks import check_pending_payments as new_check_pending_payments
    return new_check_pending_payments()


@shared_task
def check_vip_loyalty():
    """
    Otorga beneficios VIP automáticos a usuarios que han mantenido la membresía.
    Prioriza créditos si están configurados; de lo contrario usa vouchers.
    """
    settings_obj = GlobalSettings.load()
    credit_reward = settings_obj.vip_loyalty_credit_reward
    loyalty_service = settings_obj.loyalty_voucher_service

    if credit_reward <= 0 and not loyalty_service:
        return "No hay recompensa de lealtad configurada (ni créditos ni servicio)."

    required_months = max(1, settings_obj.loyalty_months_required)
    # Fecha de corte: usuario debe ser VIP desde hace al menos X meses
    eligibility_cutoff = timezone.now().date() - timedelta(days=required_months * 30)
    
    users = CustomUser.objects.filter(
        role=CustomUser.Role.VIP,
        vip_active_since__isnull=False,
        vip_active_since__lte=eligibility_cutoff,
    )
    
    rewards_issued = 0
    for user in users:
        # Verificar última recompensa para no duplicar en el ciclo actual
        last_reward = LoyaltyRewardLog.objects.filter(
            user=user).order_by('-rewarded_at').first()
        
        # Si ya recibió recompensa recientemente (dentro del periodo actual de lealtad)
        # La lógica es: si la última recompensa fue hace MENOS de required_months, esperar.
        if last_reward:
             # Aproximación simple de meses: 30 días
             days_since_reward = (timezone.now().date() - last_reward.rewarded_at).days
             if days_since_reward < (required_months * 30):
                 continue

        # Otorgar recompensa
        if credit_reward > 0:
            # Opción 1: Créditos (Prioridad)
            try:
                credit = ClientCredit.objects.create(
                    user=user,
                    initial_amount=credit_reward,
                    remaining_amount=credit_reward,
                    status=ClientCredit.CreditStatus.AVAILABLE,
                    expires_at=timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
                )
                LoyaltyRewardLog.objects.create(
                    user=user, 
                    credit=credit, 
                    rewarded_at=timezone.now().date()
                )
                AuditLog.objects.create(
                    admin_user=None,
                    target_user=user,
                    action=AuditLog.Action.LOYALTY_REWARD_ISSUED,
                    details=f"Crédito de lealtad otorgado automáticamente: {credit_reward}",
                )
                rewards_issued += 1
            except Exception as e:
                logger.error("Error otorgando crédito de lealtad a usuario %s: %s", user.id, e)
                
        elif loyalty_service:
            # Opción 2: Vouchers (Legacy fallback)
            try:
                voucher = Voucher.objects.create(
                    user=user,
                    service=loyalty_service,
                    expires_at=timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days),
                )
                LoyaltyRewardLog.objects.create(
                    user=user, voucher=voucher, rewarded_at=timezone.now().date())
                AuditLog.objects.create(
                    admin_user=None,
                    target_user=user,
                    action=AuditLog.Action.LOYALTY_REWARD_ISSUED,
                    details=f"Voucher de lealtad otorgado a {user.id}",
                )
                rewards_issued += 1
            except Exception as e:
                logger.error("Error otorgando voucher de lealtad a usuario %s: %s", user.id, e)

    return f"Recompensas de lealtad emitidas: {rewards_issued}"


# MIGRADO A finances.tasks.process_recurring_subscriptions
# Esta función se mantiene solo para compatibilidad temporal
@shared_task
def process_recurring_subscriptions():
    """
    DEPRECADO: Migrado a finances.tasks.process_recurring_subscriptions

    Intenta cobrar y extender suscripciones VIP que están por vencer.
    """
    from finances.tasks import process_recurring_subscriptions as new_process_recurring_subscriptions
    return new_process_recurring_subscriptions()


# MIGRADO A finances.tasks.downgrade_expired_vips
# Esta función se mantiene solo para compatibilidad temporal
@shared_task
def downgrade_expired_vips():
    """
    DEPRECADO: Migrado a finances.tasks.downgrade_expired_vips

    Degrada usuarios VIP cuyo período expiró.
    """
    from finances.tasks import downgrade_expired_vips as new_downgrade_expired_vips
    return new_downgrade_expired_vips()





@shared_task
def cleanup_old_appointments(days_to_keep=730):
    """
    Archiva o elimina citas completadas/canceladas antiguas para contener el tamaño de la base.
    """
    cutoff = timezone.now() - timedelta(days=days_to_keep)
    old = Appointment.objects.filter(
        status__in=[
            Appointment.AppointmentStatus.COMPLETED,
            Appointment.AppointmentStatus.CANCELLED,
        ],
        updated_at__lt=cutoff,
    )
    count = old.count()
    if count:
        old.delete()
        logger.info("Limpieza de citas antiguas: %s registros eliminados (>%d días)", count, days_to_keep)
    return {"deleted": count, "cutoff": cutoff.isoformat()}


@shared_task
def cleanup_webhook_events(days_to_keep=30):
    """
    Elimina eventos de webhook antiguos para mantener la tabla limpia.
    """
    from finances.models import WebhookEvent
    cutoff = timezone.now() - timedelta(days=days_to_keep)
    old_events = WebhookEvent.objects.filter(created_at__lt=cutoff)
    count = old_events.count()
    if count:
        old_events.delete()
        logger.info("Limpieza de WebhookEvents: %s registros eliminados (>%d días)", count, days_to_keep)
    return {"deleted": count, "cutoff": cutoff.isoformat()}
