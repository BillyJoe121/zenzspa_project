import uuid
from django.db import models
from django.conf import settings


class BaseModel(models.Model):
    """
    Modelo base abstracto que proporciona campos comunes para otros modelos.

    Atributos:
        id (UUIDField): Clave primaria única universal para el registro.
        created_at (DateTimeField): Marca de tiempo de la creación del registro.
        updated_at (DateTimeField): Marca de tiempo de la última actualización del registro.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class AuditLog(BaseModel):
    """
    Modelo para registrar acciones significativas realizadas en el sistema,
    principalmente por administradores.
    """
    class Action(models.TextChoices):
        FLAG_NON_GRATA = 'FLAG_NON_GRATA', 'Marcar como Persona No Grata'
        ADMIN_CANCEL_APPOINTMENT = 'ADMIN_CANCEL_APPOINTMENT', 'Admin cancela cita pagada'
        APPOINTMENT_CANCELLED_BY_ADMIN = 'APPOINTMENT_CANCELLED_BY_ADMIN', 'Appointment Cancelled by Admin'
        # Se pueden añadir más acciones en el futuro

    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        verbose_name="Acción Realizada"
    )
    # El administrador que realizó la acción. Si se borra, el log permanece.
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs_performed',
        verbose_name="Usuario Admin"
    )
    # El usuario sobre el cual se realizó la acción.
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs_received',
        verbose_name="Usuario Objetivo"
    )
    target_appointment = models.ForeignKey(
        'spa.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Link to a specific appointment related to the action."
    )
    details = models.TextField(
        blank=True,
        verbose_name="Detalles Adicionales"
    )

    def __str__(self):
        return f"Acción '{self.get_action_display()}' por '{self.admin_user}' a las {self.created_at.strftime('%Y-%m-%d %H:%M')}"  # pylint: disable=no-member

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ['-created_at']
