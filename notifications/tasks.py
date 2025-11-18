import logging
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import NotificationLog, NotificationTemplate
from notifications.services import NotificationService
from spa.models import Appointment

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_notification_task(self, log_id):
    from notifications.models import NotificationLog

    try:
        log = NotificationLog.objects.select_related("user").get(id=log_id)
    except NotificationLog.DoesNotExist:
        return "Log desaparecido"

    if log.status == NotificationLog.Status.SENT:
        return "Ya enviado"

    if log.status == NotificationLog.Status.SILENCED:
        log.status = NotificationLog.Status.QUEUED
        log.save(update_fields=["status", "updated_at"])

    try:
        _dispatch_channel(log)
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
        log.error_message = ""
        log.save(update_fields=["status", "sent_at", "error_message", "updated_at"])
        return "Enviado"
    except Exception as exc:
        metadata = log.metadata or {}
        attempts = metadata.get("attempts", 0) + 1
        metadata["attempts"] = attempts
        max_attempts = metadata.get("max_attempts") or NotificationService.MAX_DELIVERY_ATTEMPTS
        metadata["max_attempts"] = max_attempts
        log.metadata = metadata
        log.status = NotificationLog.Status.FAILED
        log.error_message = str(exc)
        log.save(update_fields=["status", "error_message", "metadata", "updated_at"])
        if attempts >= max_attempts:
            metadata["dead_letter"] = True
            log.metadata = metadata
            log.save(update_fields=["metadata"])
            logger.error("Notificación %s enviada a DLQ después de %s intentos", log.id, attempts)
            return "dead_letter"
        fallback = metadata.get("fallback") or []
        fallback_used = metadata.get("fallback_attempted", False)
        if fallback and not fallback_used:
            metadata["fallback_attempted"] = True
            log.metadata = metadata
            log.save(update_fields=["metadata"])
            NotificationService.send_notification(
                user=log.user,
                event_code=log.event_code,
                context=(metadata.get("context") or {}),
                priority=log.priority,
                channel_override=fallback[0],
                fallback_channels=fallback[1:],
            )
        logger.exception("Error enviando notificación %s", log.id)
        raise


def _dispatch_channel(log):
    channel = log.channel
    payload = log.payload or {}
    user = log.user
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if channel == NotificationTemplate.ChannelChoices.EMAIL:
        recipient = getattr(user, "email", None)
        if not recipient:
            raise ValueError("El usuario no tiene email.")
        send_mail(
            subject or f"[ZenzSpa] {log.event_code.replace('_', ' ').title()}",
            body,
            None,
            [recipient],
            fail_silently=False,
        )
    elif channel == NotificationTemplate.ChannelChoices.SMS:
        phone = getattr(user, "phone_number", None)
        if not phone:
            raise ValueError("El usuario no tiene teléfono.")
        logger.info("SMS a %s: %s", mask_contact(phone), body)
    elif channel == NotificationTemplate.ChannelChoices.PUSH:
        logger.info("Push para %s: %s", user_id_display(user), body)
    else:
        raise ValueError(f"Canal desconocido {channel}")


def user_id_display(user):
    if not user:
        return "anon"
    return mask_contact(user.phone_number or user.email or str(user.pk))


def mask_contact(value):
    if not value:
        return "***"
    if "@" in value:
        local, domain = value.split("@", 1)
        if len(local) <= 2:
            masked_local = "***"
        else:
            masked_local = f"{local[0]}***{local[-1]}"
        return f"{masked_local}@{domain}"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


@shared_task
def check_upcoming_appointments_2h():
    now = timezone.now()
    window_start = now + timedelta(hours=2)
    window_end = window_start + timedelta(minutes=5)
    from spa.models import Appointment

    appointments = Appointment.objects.select_related("user").filter(
        start_time__gte=window_start,
        start_time__lte=window_end,
        status__in=[
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ],
    )
    count = 0
    for appointment in appointments:
        context = {
            "appointment_id": str(appointment.id),
            "start_time": appointment.start_time.isoformat(),
            "services": appointment.get_service_names(),
        }
        NotificationService.send_notification(
            user=appointment.user,
            event_code="APPOINTMENT_REMINDER_2H",
            context=context,
            priority="high",
        )
        count += 1
    return f"{count} recordatorios generados"
