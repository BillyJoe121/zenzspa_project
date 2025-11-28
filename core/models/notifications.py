"""
Modelo de notificaciones administrativas del sistema.
"""
from django.db import models

from .base import BaseModel


class AdminNotification(BaseModel):
    class NotificationType(models.TextChoices):
        PAGOS = "PAGOS", "Pagos"
        SUSCRIPCIONES = "SUSCRIPCIONES", "Suscripciones"
        USUARIOS = "USUARIOS", "Usuarios"

    class NotificationSubtype(models.TextChoices):
        PAGO_EXITOSO = "PAGO_EXITOSO", "Pago exitoso"
        PAGO_FALLIDO = "PAGO_FALLIDO", "Pago fallido"
        USUARIO_CNG = "USUARIO_CNG", "Usuario marcado como CNG"
        USUARIO_RECURRENTE = "USUARIO_RECURRENTE", "Usuario recurrente"
        OTRO = "OTRO", "Otro"

    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.USUARIOS,
    )
    subtype = models.CharField(
        max_length=30,
        choices=NotificationSubtype.choices,
        default=NotificationSubtype.OTRO,
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Notificación Administrativa"
        verbose_name_plural = "Notificaciones Administrativas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.title}"
