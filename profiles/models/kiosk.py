import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from .clinical import ClinicalProfile


class KioskSession(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activa"
        LOCKED = "LOCKED", "Bloqueada"
        COMPLETED = "COMPLETED", "Completada"

    profile = models.ForeignKey(
        ClinicalProfile,
        on_delete=models.CASCADE,
        related_name="kiosk_sessions",
    )
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kiosk_sessions_started",
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    has_pending_changes = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Sesión de Quiosco"
        verbose_name_plural = "Sesiones de Quiosco"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["profile", "created_at"]),
            models.Index(fields=["staff_member", "created_at"]),
        ]

    def __str__(self):
        return f"Sesión para {self.profile.user} expira {self.expires_at}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        if self.status == self.Status.ACTIVE:
            self.is_active = True
            self.locked = False
        elif self.status == self.Status.LOCKED:
            self.is_active = False
            self.locked = True
        else:
            self.is_active = False
            self.locked = False
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == self.Status.ACTIVE and not self.has_expired

    @property
    def has_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def remaining_seconds(self):
        delta = (self.expires_at - timezone.now()).total_seconds()
        return max(int(delta), 0)

    def deactivate(self):
        if self.status != self.Status.COMPLETED:
            self.status = self.Status.COMPLETED
            self.has_pending_changes = False
            self.save(update_fields=["status", "is_active", "locked", "has_pending_changes", "updated_at"])

    def lock(self):
        if self.status != self.Status.LOCKED:
            self.status = self.Status.LOCKED
            self.has_pending_changes = False
            self.save(update_fields=["status", "is_active", "locked", "has_pending_changes", "updated_at"])

    def mark_expired(self):
        if self.has_expired and self.status == self.Status.ACTIVE:
            self.lock()

    def heartbeat(self):
        if self.status == self.Status.ACTIVE:
            self.last_activity = timezone.now()
            self.save(update_fields=["last_activity", "updated_at"])

    def mark_pending_changes(self):
        if not self.has_pending_changes:
            self.has_pending_changes = True
            self.save(update_fields=["has_pending_changes", "updated_at"])

    def clear_pending_changes(self):
        if self.has_pending_changes:
            self.has_pending_changes = False
            self.save(update_fields=["has_pending_changes", "updated_at"])
