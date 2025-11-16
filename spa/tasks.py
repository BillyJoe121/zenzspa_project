import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail

from core.models import GlobalSettings, AuditLog
from users.models import CustomUser
from .models import Appointment, WaitlistEntry, Payment, Voucher, LoyaltyRewardLog
from .services import PaymentService

# Se obtiene una instancia del logger.
logger = logging.getLogger(__name__)


@shared_task
def _send_reminder_for_appointment(appointment_id):
    """
    Tarea auxiliar que envía el correo para una cita específica.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        if not appointment.user.email:
            logger.warning("Recordatorio no enviado para cita %s: sin email.", appointment_id)
            return

        subject = "Recordatorio de tu cita en ZenzSpa - Mañana"
        start_time_local = appointment.start_time.astimezone(timezone.get_current_timezone())
        services = appointment.get_service_names()
        message = (
            f"Hola {appointment.user.first_name},\n\n"
            f"Este es un recordatorio de tu cita en ZenzSpa para los servicios '{services}'.\n"
            f"Tu cita es mañana, {start_time_local.strftime('%d de %B')} a las {start_time_local.strftime('%I:%M %p')}.\n\n"
            f"¡Te esperamos!\n\n"
            f"El equipo de ZenzSpa"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[appointment.user.email],
            fail_silently=False,
        )
        logger.info("Recordatorio enviado para la cita %s", appointment_id)
    except Appointment.DoesNotExist:
        logger.error("No se encontró la cita %s para enviar recordatorio.", appointment_id)


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
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    for appointment in appointments:
        _send_reminder_for_appointment.delay(str(appointment.id))
    logger.info("Se programaron %s recordatorios de citas.", appointments.count())


@shared_task
def notify_waitlist_availability(waitlist_entry_id):
    """
    Notifica al usuario de la lista de espera cuando se libera un horario.
    """
    try:
        entry = WaitlistEntry.objects.select_related('user').get(id=waitlist_entry_id)
    except WaitlistEntry.DoesNotExist:
        logger.error("La entrada de lista de espera %s no existe.", waitlist_entry_id)
        return

    user = entry.user
    message = (
        f"Hola {user.first_name},\n\n"
        "Se ha liberado un horario que coincide con tu solicitud en la lista de espera.\n"
        "Ingresa a la app para confirmarlo antes de que expire.\n\n"
        "Equipo ZenzSpa"
    )
    if user.email:
        send_mail(
            subject="Disponibilidad en la lista de espera",
            message=message,
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )
    logger.info("Notificación de lista de espera enviada a %s", user.email or user.phone_number)


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
        status=Appointment.AppointmentStatus.PENDING_ADVANCE,
        created_at__lt=time_threshold,
    )

    if not unpaid_appointments.exists():
        return "No hay citas pendientes de pago para cancelar."

    cancelled_count = 0
    for appt in unpaid_appointments:
        appt.status = Appointment.AppointmentStatus.CANCELLED_BY_SYSTEM
        appt.save(update_fields=['status', 'updated_at'])
        WaitlistService.offer_slot_for_appointment(appt)
        logger.info(
            "Cita %s cancelada por falta de pago; se notificó a la lista de espera.",
            appt.id,
        )
        cancelled_count += 1

    return f"{cancelled_count} citas pendientes de anticipo han sido canceladas."


@shared_task
def check_pending_payments():
    """
    Verifica pagos pendientes que podrían haberse quedado sin webhook.
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
def check_vip_loyalty():
    """
    Otorga beneficios VIP automáticos a usuarios que han mantenido la membresía.
    """
    settings_obj = GlobalSettings.load()
    loyalty_service = settings_obj.loyalty_voucher_service
    if not loyalty_service:
        return "No hay servicio configurado para recompensas."
    required_months = max(1, settings_obj.loyalty_months_required)
    window = timezone.now().date() - timedelta(days=required_months * 30)
    users = CustomUser.objects.filter(
        role=CustomUser.Role.VIP,
        vip_active_since__isnull=False,
        vip_active_since__lte=window,
    )
    rewards = 0
    for user in users:
        last_reward = LoyaltyRewardLog.objects.filter(user=user).order_by('-rewarded_at').first()
        if last_reward and last_reward.rewarded_at >= window:
            continue
        voucher = Voucher.objects.create(
            user=user,
            service=loyalty_service,
            expires_at=timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days),
        )
        LoyaltyRewardLog.objects.create(user=user, voucher=voucher, rewarded_at=timezone.now().date())
        AuditLog.objects.create(
            admin_user=None,
            target_user=user,
            action=AuditLog.Action.LOYALTY_REWARD_ISSUED,
            details=f"Voucher de lealtad otorgado a {user.id}",
        )
        rewards += 1
    return f"Recompensas emitidas: {rewards}"


@shared_task
def process_recurring_subscriptions():
    """
    Intenta cobrar y extender suscripciones VIP que están por vencer.
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
        payment = Payment.objects.create(
            user=user,
            amount=vip_price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.VIP_SUBSCRIPTION,
            transaction_id=reference,
        )
        if user.vip_payment_token:
            PaymentService.apply_gateway_status(payment, 'APPROVED', {'id': reference, 'status': 'APPROVED'})
            user.vip_failed_payments = 0
            user.save(update_fields=['vip_failed_payments', 'updated_at'])
            processed += 1
        else:
            PaymentService.apply_gateway_status(payment, 'DECLINED', {'id': reference, 'status': 'DECLINED'})
            user.vip_failed_payments += 1
            if user.vip_failed_payments >= 3:
                user.vip_auto_renew = False
            user.save(update_fields=['vip_failed_payments', 'vip_auto_renew', 'updated_at'])
    return f"Renovaciones intentadas: {processed}"


@shared_task
def downgrade_expired_vips():
    """
    Degrada usuarios VIP cuyo período expiró.
    """
    today = timezone.now().date()
    expired_users = CustomUser.objects.filter(
        role=CustomUser.Role.VIP,
        vip_expires_at__isnull=False,
        vip_expires_at__lt=today,
    )
    count = 0
    for user in expired_users:
        user.role = CustomUser.Role.CLIENT
        user.vip_auto_renew = False
        user.vip_active_since = None
        user.vip_failed_payments = 0
        user.save(update_fields=['role', 'vip_auto_renew', 'vip_active_since', 'vip_failed_payments', 'updated_at'])
        AuditLog.objects.create(
            admin_user=None,
            target_user=user,
            action=AuditLog.Action.VIP_DOWNGRADED,
            details=f"Usuario {user.id} degradado a CLIENT por expiración VIP.",
        )
        count += 1
    return f"Usuarios degradados: {count}"
