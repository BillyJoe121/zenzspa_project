import logging
from datetime import timedelta

from django.template import Context, Template, TemplateSyntaxError, VariableDoesNotExist
from django.utils import timezone

from notifications.models import (
    NotificationPreference,
    NotificationTemplate,
    NotificationLog,
)

logger = logging.getLogger(__name__)


class NotificationRenderer:
    @staticmethod
    def render(template_obj, context):
        """
        Renderiza template con contexto.
        Maneja errores de sintaxis y variables faltantes.
        """
        ctx = Context(context or {})
        subject = ""
        body = ""

        try:
            if template_obj.subject_template:
                subject = Template(template_obj.subject_template).render(ctx).strip()
            body = Template(template_obj.body_template).render(ctx).strip()

        except TemplateSyntaxError as e:
            logger.error(
                "Error de sintaxis en template %s: %s",
                template_obj.event_code,
                str(e)
            )
            raise ValueError(f"Template inválido: {str(e)}")

        except VariableDoesNotExist as e:
            # No fallar por variables faltantes, solo advertir
            logger.warning(
                "Variable faltante en template %s: %s. Context keys: %s",
                template_obj.event_code,
                str(e),
                list(context.keys()) if context else []
            )
            # Continuar con el render parcial

        except Exception as e:
            logger.exception(
                "Error inesperado renderizando template %s",
                template_obj.event_code
            )
            raise

        return subject, body


class NotificationService:
    CHANNEL_PRIORITY = [
        NotificationTemplate.ChannelChoices.WHATSAPP,  # Primero WhatsApp
        NotificationTemplate.ChannelChoices.EMAIL,      # Fallback a Email
        # SMS y PUSH deshabilitados
    ]
    MAX_DELIVERY_ATTEMPTS = 3

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
            # Allow anonymous if phone_number is in context
            if not context or not context.get("phone_number"):
                return None
            # If user is None, we can't check preferences easily. 
            # We assume WhatsApp is enabled for anonymous users if phone is provided.
            # We need a dummy preference or skip preference check.
        
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

        if user:
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
        else:
            # Anonymous user: Assume all channels in templates are available (or just WhatsApp)
            available = [(chan, tmpl) for chan, tmpl in templates]
            # We might want to restrict to WhatsApp only for anonymous
            available = [x for x in available if x[0] == NotificationTemplate.ChannelChoices.WHATSAPP]
            
            if not available:
                 # Log failure for anonymous?
                 return None

        fallback = fallback_channels or [chan for chan, _ in available[1:]]
        channel, template = available[0]
        subject, body = NotificationRenderer.render(template, context or {})
        eta = None
        
        within_quiet = False
        if user:
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
        metadata_dict = {
            "context": context,
            "fallback": fallback_channels,
            "scheduled_for": eta.isoformat() if eta else None,
            "attempts": 0,
            "max_attempts": cls.MAX_DELIVERY_ATTEMPTS,
            "dead_letter": False,
        }
        
        # Lift phone_number to top-level metadata if present
        if context and "phone_number" in context:
            metadata_dict["phone_number"] = context["phone_number"]

        log = NotificationLog.objects.create(
            user=user,
            event_code=event_code,
            channel=channel,
            status=NotificationLog.Status.SILENCED if silenced else NotificationLog.Status.QUEUED,
            priority=priority,
            payload={"subject": subject, "body": body},
            metadata=metadata_dict,
        )
        from .tasks import send_notification_task

        kwargs = {}
        if eta:
            kwargs["eta"] = eta + timedelta(seconds=1)
        send_notification_task.apply_async(args=[str(log.id)], **kwargs)
        return log
