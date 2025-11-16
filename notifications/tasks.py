import logging
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import NotificationLog, NotificationTemplate
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
        log.status = NotificationLog.Status.FAILED
        log.error_message = str(exc)
        log.save(update_fields=["status", "error_message", "updated_at"])
        fallback = (log.metadata or {}).get("fallback") or []
        if fallback:
            from notifications.services import NotificationService

            NotificationService.send_notification(
                user=log.user,
                event_code=log.event_code,
                context=(log.metadata or {}).get("context") or {},
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
        logger.info("SMS a %s: %s", phone, body)
    elif channel == NotificationTemplate.ChannelChoices.PUSH:
        logger.info("Push para %s: %s", user_id_display(user), body)
    else:
        raise ValueError(f"Canal desconocido {channel}")


def user_id_display(user):
    if not user:
        return "anon"
    return user.phone_number or user.email or str(user.pk)


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
