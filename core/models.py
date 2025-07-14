import uuid
from django.db import models
from django.conf import settings
from django.core.cache import cache

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class AuditLog(BaseModel):
    class Action(models.TextChoices):
        FLAG_NON_GRATA = 'FLAG_NON_GRATA', 'Marcar como Persona No Grata'
        ADMIN_CANCEL_APPOINTMENT = 'ADMIN_CANCEL_APPOINTMENT', 'Admin cancela cita pagada'
        APPOINTMENT_CANCELLED_BY_ADMIN = 'APPOINTMENT_CANCELLED_BY_ADMIN', 'Appointment Cancelled by Admin'

    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        verbose_name="Acción Realizada"
    )
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs_performed',
        verbose_name="Usuario Admin"
    )
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
        return f"Acción '{self.get_action_display()}' por '{self.admin_user}' a las {self.created_at.strftime('%Y-%m-%d %H:%M')}" # pylint: disable=no-member

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ['-created_at']

# --- INICIO DE LA MODIFICACIÓN ---

class GlobalSettings(BaseModel):
    """
    Modelo Singleton para almacenar las configuraciones globales del sistema.
    Solo debe existir una única instancia de este modelo.
    """
    low_supervision_capacity = models.PositiveIntegerField(
        default=1,
        verbose_name="Capacidad Máxima para Servicios de Baja Supervisión",
        help_text="Número máximo de citas de baja supervisión que pueden ocurrir simultáneamente."
    )
    # Aquí se pueden añadir más configuraciones globales en el futuro.
    # Ejemplo: appointment_buffer_time = models.PositiveIntegerField(default=10, ...)

    def save(self, *args, **kwargs):
        """
        Asegura que solo exista una instancia de este modelo.
        """
        self.pk = self.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        super().save(*args, **kwargs)
        # Invalida la caché cada vez que se guardan las configuraciones
        cache.delete('global_settings')

    @classmethod
    def load(cls):
        """
        Carga la instancia de configuración desde la caché o la base de datos.
        """
        # Intenta obtener de la caché primero
        settings_instance = cache.get('global_settings')
        if settings_instance is None:
            # Si no está en caché, obténla de la DB y guárdala en caché
            settings_instance, _ = cls.objects.get_or_create(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001")
            )
            cache.set('global_settings', settings_instance)
        return settings_instance

    def __str__(self):
        return "Configuraciones Globales del Sistema"

    class Meta:
        verbose_name = "Configuración Global"
        verbose_name_plural = "Configuraciones Globales"
# --- FIN DE LA MODIFICACIÓN ---