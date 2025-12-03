from datetime import datetime, time, timedelta, timezone as py_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords

from core.models import BaseModel


class NotificationPreference(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(
        default=False,
        editable=False,
        help_text="SMS no disponible - usar WhatsApp"
    )
    push_enabled = models.BooleanField(
        default=False,
        editable=False,
        help_text="Push no disponible actualmente"
    )
    whatsapp_enabled = models.BooleanField(
        default=True,
        help_text="Notificaciones por WhatsApp"
    )
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="America/Bogota")

    class Meta:
        verbose_name = "Preferencia de Notificación"
        verbose_name_plural = "Preferencias de Notificación"

    def __str__(self):
        return f"Preferencias de {self.user}"

    @property
    def tzinfo(self):
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return timezone.get_current_timezone()

    def is_quiet_now(self, moment=None):
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        moment = moment or timezone.now()
        tz = self.tzinfo
        local_moment = moment.astimezone(tz)
        start_dt = datetime.combine(local_moment.date(), self.quiet_hours_start, tz)
        end_dt = datetime.combine(local_moment.date(), self.quiet_hours_end, tz)
        if self.quiet_hours_start < self.quiet_hours_end:
            return start_dt <= local_moment < end_dt
        return local_moment >= start_dt or local_moment < end_dt

    def next_quiet_end(self, moment=None):
        if not self.quiet_hours_end:
            return None
        moment = moment or timezone.now()
        tz = self.tzinfo
        local_moment = moment.astimezone(tz)
        end_dt = datetime.combine(local_moment.date(), self.quiet_hours_end, tz)
        if self.quiet_hours_start and self.quiet_hours_start >= self.quiet_hours_end:
            if local_moment >= datetime.combine(local_moment.date(), self.quiet_hours_start, tz):
                end_dt = end_dt + timedelta(days=1)
        if local_moment >= end_dt:
            end_dt = end_dt + timedelta(days=1)
        return end_dt.astimezone(py_timezone.utc)

    @classmethod
    def for_user(cls, user):
        preference, _ = cls.objects.get_or_create(user=user)
        return preference

    def channel_enabled(self, channel):
        mapping = {
            NotificationTemplate.ChannelChoices.EMAIL: self.email_enabled,
            NotificationTemplate.ChannelChoices.SMS: self.sms_enabled,
            NotificationTemplate.ChannelChoices.PUSH: self.push_enabled,
            NotificationTemplate.ChannelChoices.WHATSAPP: self.whatsapp_enabled,
        }
        return mapping.get(channel, False)

    def clean(self):
        super().clean()

        # Validar timezone
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except Exception:
                raise ValidationError({
                    "timezone": f"Timezone inválido: {self.timezone}. "
                               f"Use valores como 'America/Bogota', 'America/Mexico_City', etc."
                })

        # Validaciones de quiet hours
        if self.quiet_hours_start and self.quiet_hours_end:
            if self.quiet_hours_start == self.quiet_hours_end:
                raise ValidationError(
                    {"quiet_hours_start": "El rango de silencio debe tener duración mayor a cero."}
                )
        elif self.quiet_hours_start or self.quiet_hours_end:
            raise ValidationError(
                {"quiet_hours_start": "Debes definir inicio y fin de quiet hours."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class NotificationTemplate(BaseModel):
    class ChannelChoices(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        PUSH = "PUSH", "Push"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    event_code = models.SlugField(max_length=64)
    channel = models.CharField(max_length=10, choices=ChannelChoices.choices)
    subject_template = models.TextField(blank=True)
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Plantilla de Notificación"
        verbose_name_plural = "Plantillas de Notificación"
        unique_together = ("event_code", "channel", "created_at")
        indexes = [
            models.Index(fields=["event_code", "channel", "is_active"]),
        ]

    def __str__(self):
        return f"{self.event_code} ({self.channel})"

    def clean(self):
        super().clean()
        if not self.body_template or not self.body_template.strip():
            raise ValidationError({"body_template": "El cuerpo de la plantilla no puede estar vacío."})
        if len(self.body_template) > 8000:
            raise ValidationError({"body_template": "El cuerpo de la plantilla excede el límite de 8000 caracteres."})
        if self.channel != self.ChannelChoices.WHATSAPP and not self.subject_template:
            raise ValidationError({"subject_template": "El asunto es requerido para canales distintos a WhatsApp."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class NotificationLog(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Encolada"
        SENT = "SENT", "Enviada"
        FAILED = "FAILED", "Fallida"
        SILENCED = "SILENCED", "Pospuesta por silencio"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="notification_logs",
    )
    event_code = models.SlugField(max_length=64)
    channel = models.CharField(max_length=10, choices=NotificationTemplate.ChannelChoices.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    priority = models.CharField(max_length=16, default="high")
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Registro de Notificación"
        verbose_name_plural = "Registros de Notificación"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['event_code', 'channel']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status', 'sent_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.event_code} -> {self.channel} ({self.status})"
