"""
Modelo de claves de idempotencia para operaciones críticas.
"""
from django.conf import settings
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone

from .base import BaseModel


class IdempotencyKey(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        COMPLETED = "COMPLETED", "Completado"

    key = models.CharField(
        max_length=255,
        unique=True,
        validators=[MinLengthValidator(16)]
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="idempotency_keys",
    )
    endpoint = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    response_body = models.JSONField(null=True, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "Idempotency Key"
        verbose_name_plural = "Idempotency Keys"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["status", "completed_at"]),
            models.Index(fields=["status", "locked_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["request_hash"]),
        ]

    def mark_processing(self):
        self.status = self.Status.PENDING
        self.locked_at = timezone.now()
        self.save(update_fields=["status", "locked_at", "updated_at"])

    def mark_completed(self, *, response_body, status_code):
        self.status = self.Status.COMPLETED
        self.response_body = response_body
        self.status_code = status_code
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "response_body",
                "status_code",
                "completed_at",
                "updated_at",
            ]
        )
