import uuid
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


GLOBAL_SETTINGS_CACHE_KEY = "core:global_settings:v1"
GLOBAL_SETTINGS_SINGLETON_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AuditLog(BaseModel):
    class Action(models.TextChoices):
        FLAG_NON_GRATA = "FLAG_NON_GRATA", "Marcar como Persona No Grata"
        ADMIN_CANCEL_APPOINTMENT = "ADMIN_CANCEL_APPOINTMENT", "Admin cancela cita pagada"
        APPOINTMENT_CANCELLED_BY_ADMIN = "APPOINTMENT_CANCELLED_BY_ADMIN", "Appointment Cancelled by Admin"

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

    def __str__(self) -> str:  # pylint: disable=no-member
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


class GlobalSettings(BaseModel):
    """
    Modelo Singleton para almacenar las configuraciones globales del sistema.
    Se guarda con un UUID fijo y se cachea en memoria para lecturas rápidas.
    """
    low_supervision_capacity = models.PositiveIntegerField(
        default=1,
        verbose_name="Capacidad Máxima para Servicios de Baja Supervisión",
        help_text="Número máximo de citas de baja supervisión que pueden ocurrir simultáneamente.",
    )
    advance_payment_percentage = models.PositiveIntegerField(
        default=20,
        verbose_name="Porcentaje de Anticipo Requerido (%)",
        help_text="Porcentaje del costo total de la cita que se debe pagar como anticipo.",
    )
    appointment_buffer_time = models.PositiveIntegerField(
        default=10,
        verbose_name="Tiempo de Limpieza entre Citas (minutos)",
        help_text="Minutos de búfer que se añadirán después de cada cita para preparación.",
    )

    # Validaciones de dominio (evita valores absurdos en producción)
    def clean(self):
        errors = {}
        if self.advance_payment_percentage > 100:
            errors["advance_payment_percentage"] = "Debe estar entre 0 y 100."
        if self.low_supervision_capacity < 1:
            errors["low_supervision_capacity"] = "Debe ser al menos 1."
        if self.appointment_buffer_time > 180:
            errors["appointment_buffer_time"] = "No debería exceder 180 minutos."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Forzamos UUID singleton
        self.pk = self.id = GLOBAL_SETTINGS_SINGLETON_UUID
        self.full_clean()
        super().save(*args, **kwargs)
        # Invalida/actualiza caché después de guardar
        cache.set(GLOBAL_SETTINGS_CACHE_KEY, self, timeout=None)

    @classmethod
    def load(cls) -> "GlobalSettings":
        """
        Obtiene la instancia desde caché o DB, creándola si no existe.
        """
        cached = cache.get(GLOBAL_SETTINGS_CACHE_KEY)
        if cached is not None:
            return cached

        obj, _ = cls.objects.get_or_create(id=GLOBAL_SETTINGS_SINGLETON_UUID)
        # Asegura timestamps coherentes en primer create
        if not obj.created_at:
            obj.created_at = timezone.now()
            obj.save(update_fields=["created_at"])
        cache.set(GLOBAL_SETTINGS_CACHE_KEY, obj, timeout=None)
        return obj

    def __str__(self) -> str:
        return "Configuraciones Globales del Sistema"

    class Meta:
        verbose_name = "Configuración Global"
        verbose_name_plural = "Configuraciones Globales"
        # Ayuda en búsquedas y ordenaciones
        indexes = [
            models.Index(fields=["updated_at"]),
        ]
