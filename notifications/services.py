from datetime import timedelta

from django.template import Context, Template
from django.utils import timezone

from notifications.models import (
    NotificationPreference,
    NotificationTemplate,
    NotificationLog,
)


class NotificationRenderer:
    @staticmethod
    def render(template_obj, context):
        ctx = Context(context or {})
        subject = ""
        if template_obj.subject_template:
            subject = Template(template_obj.subject_template).render(ctx).strip()
        body = Template(template_obj.body_template).render(ctx).strip()
        return subject, body


class NotificationService:
    CHANNEL_PRIORITY = [
        NotificationTemplate.ChannelChoices.EMAIL,
        NotificationTemplate.ChannelChoices.SMS,
        NotificationTemplate.ChannelChoices.PUSH,
    ]

    @classmethod
    def send_notification(
        cls,
        user,
        event_code,
        context=None,
        priority="high",
        channel_override=None,
        fallback_channels=None,
    ):
        if user is None:
            return None
        templates = cls._get_templates(event_code, channel_override)
        if not templates:
            NotificationLog.objects.create(
                user=user,
                event_code=event_code,
                channel=NotificationTemplate.ChannelChoices.EMAIL,
                status=NotificationLog.Status.FAILED,
                error_message="No existe plantilla activa para el evento.",
                priority=priority,
            )
            return None

        preference = NotificationPreference.for_user(user)
        available = []
        for channel, template in templates:
            if not preference.channel_enabled(channel):
                continue
            available.append((channel, template))

        if not available:
            NotificationLog.objects.create(
                user=user,
                event_code=event_code,
                channel=templates[0][0],
                status=NotificationLog.Status.FAILED,
                error_message="El usuario no tiene canales habilitados.",
                priority=priority,
            )
            return None

        fallback = fallback_channels or [chan for chan, _ in available[1:]]
        channel, template = available[0]
        subject, body = NotificationRenderer.render(template, context or {})
        eta = None
        within_quiet = preference.is_quiet_now() and priority != "critical"
        if within_quiet:
            eta = preference.next_quiet_end()
        return cls._enqueue_log(
            user=user,
            event_code=event_code,
            channel=channel,
            subject=subject,
            body=body,
            context=context or {},
            priority=priority,
            fallback_channels=fallback,
            eta=eta,
            silenced=within_quiet,
        )

    @classmethod
    def _get_templates(cls, event_code, channel_override=None):
        queryset = NotificationTemplate.objects.filter(
            event_code=event_code,
            is_active=True,
        ).order_by("-created_at")
        templates = []
        for channel in cls.CHANNEL_PRIORITY:
            if channel_override and channel != channel_override:
                continue
            template = queryset.filter(channel=channel).first()
            if template:
                templates.append((channel, template))
        return templates

    @classmethod
    def _enqueue_log(
        cls,
        *,
        user,
        event_code,
        channel,
        subject,
        body,
        context,
        priority,
        fallback_channels,
        eta=None,
        silenced=False,
    ):
        log = NotificationLog.objects.create(
            user=user,
            event_code=event_code,
            channel=channel,
            status=NotificationLog.Status.SILENCED if silenced else NotificationLog.Status.QUEUED,
            priority=priority,
            payload={"subject": subject, "body": body},
            metadata={
                "context": context,
                "fallback": fallback_channels,
                "scheduled_for": eta.isoformat() if eta else None,
            },
        )
        from .tasks import send_notification_task

        kwargs = {}
        if eta:
            kwargs["eta"] = eta + timedelta(seconds=1)
        send_notification_task.apply_async(args=[str(log.id)], **kwargs)
        return log
