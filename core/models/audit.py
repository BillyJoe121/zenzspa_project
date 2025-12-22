"""
Modelo de auditoría para registro de acciones administrativas.
"""
from django.conf import settings
from django.db import models

from .base import BaseModel


class AuditLog(BaseModel):
    """Registro de auditoría para acciones administrativas y del sistema."""

    class Action(models.TextChoices):
        FLAG_NON_GRATA = "FLAG_NON_GRATA", "Marcar como Persona No Grata"
        ADMIN_CANCEL_APPOINTMENT = "ADMIN_CANCEL_APPOINTMENT", "Admin cancela cita pagada"
        ADMIN_ENDPOINT_HIT = "ADMIN_ENDPOINT_HIT", "Invocación de endpoint admin"
        APPOINTMENT_CANCELLED_BY_ADMIN = "APPOINTMENT_CANCELLED_BY_ADMIN", "Appointment Cancelled by Admin"
        SYSTEM_CANCEL = "SYSTEM_CANCEL", "Cancelación automática del sistema"
        APPOINTMENT_RESCHEDULE_FORCE = "APPOINTMENT_RESCHEDULE_FORCE", "Reagendamiento forzado por staff"
        APPOINTMENT_COMPLETED = "APPOINTMENT_COMPLETED", "Cita completada"
        CLINICAL_PROFILE_ANONYMIZED = "CLINICAL_PROFILE_ANONYMIZED", "Perfil clínico anonimizado"
        VOUCHER_REDEEMED = "VOUCHER_REDEEMED", "Voucher redimido"
        LOYALTY_REWARD_ISSUED = "LOYALTY_REWARD_ISSUED", "Recompensa de lealtad otorgada"
        VIP_DOWNGRADED = "VIP_DOWNGRADED", "VIP degradado"
        MARKETPLACE_RETURN = "MARKETPLACE_RETURN", "Devolución marketplace procesada"
        FINANCIAL_ADJUSTMENT_CREATED = "FINANCIAL_ADJUSTMENT_CREATED", "Ajuste financiero registrado"
        USER_DELETED_PERMANENTLY = "USER_DELETED_PERMANENTLY", "Usuario eliminado permanentemente"

    action = models.CharField(
        max_length=64,
        choices=Action.choices,
        verbose_name="Acción Realizada",
    )
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs_performed",
        verbose_name="Usuario Admin",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs_received",
        verbose_name="Usuario Objetivo",
    )
    target_appointment = models.ForeignKey(
        "spa.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Cita relacionada con la acción (si aplica).",
    )
    details = models.TextField(blank=True, verbose_name="Detalles Adicionales")

    def __str__(self) -> str:
        admin_display = getattr(self.admin_user, "phone_number", None) or "admin desconocido"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.get_action_display()} por {admin_display}"

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["action"]),
            models.Index(fields=["admin_user"]),
            models.Index(fields=["target_user"]),
            models.Index(fields=["target_appointment"]),
        ]
