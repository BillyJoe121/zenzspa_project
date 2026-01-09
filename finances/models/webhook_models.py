from django.db import models

from core.models import BaseModel


class WebhookEvent(BaseModel):
    """Registro de eventos de webhook recibidos de Wompi."""

    class Status(models.TextChoices):
        PROCESSED = "PROCESSED", "Procesado"
        FAILED = "FAILED", "Falló"
        IGNORED = "IGNORED", "Ignorado"

    event_type = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSED,
    )
    error_message = models.TextField(blank=True, default="")

    def __str__(self):
        return f"WebhookEvent {self.id} - {self.event_type} - {self.status}"
