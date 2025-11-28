"""
Modelo de configuración global del sistema (Singleton).
"""
import logging
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .base import BaseModel

logger = logging.getLogger(__name__)


GLOBAL_SETTINGS_CACHE_KEY = "core:global_settings:v1"
GLOBAL_SETTINGS_SINGLETON_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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
    vip_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Precio Mensual VIP",
        help_text="Costo en COP para una suscripción mensual VIP.",
    )
    advance_expiration_minutes = models.PositiveIntegerField(
        default=20,
        verbose_name="Minutos para cancelar citas sin pago",
        help_text="Tiempo máximo para pagar el anticipo antes de cancelar automáticamente.",
    )
    credit_expiration_days = models.PositiveIntegerField(
        default=365,
        verbose_name="Días de vigencia para créditos",
        help_text="Número de días antes de que un saldo a favor expire.",
    )
    return_window_days = models.PositiveIntegerField(
        default=30,
        verbose_name="Ventana de devoluciones (días)",
        help_text="Número máximo de días para aceptar devoluciones desde la entrega.",
    )

    class NoShowCreditPolicy(models.TextChoices):
        NONE = "NONE", "Sin crédito"
        PARTIAL = "PARTIAL", "Crédito parcial"
        FULL = "FULL", "Crédito total"

    no_show_credit_policy = models.CharField(
        max_length=10,
        choices=NoShowCreditPolicy.choices,
        default=NoShowCreditPolicy.NONE,
        help_text="Regla para convertir anticipos en crédito cuando hay No-Show.",
    )
    loyalty_months_required = models.PositiveIntegerField(
        default=3,
        verbose_name="Meses continuos para recompensa VIP",
        help_text="Cantidad de meses continuos como VIP para recibir un beneficio.",
    )
    loyalty_voucher_service = models.ForeignKey(
        "spa.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Servicio de recompensa VIP",
        help_text="Servicio que se otorga como voucher al cumplir la lealtad.",
    )
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Inicio de horas de silencio",
        help_text="Hora desde la cual se silencian notificaciones no críticas.",
    )
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Fin de horas de silencio",
        help_text="Hora en la que termina la ventana de silencio.",
    )
    timezone_display = models.CharField(
        max_length=64,
        default="America/Bogota",
        verbose_name="Zona horaria de visualización",
        help_text="Zona horaria usada para mostrar fechas al usuario.",
    )
    waitlist_enabled = models.BooleanField(
        default=False,
        verbose_name="Lista de espera habilitada",
        help_text="Permite activar/desactivar el módulo de lista de espera.",
    )
    waitlist_ttl_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="TTL de lista de espera (minutos)",
        help_text="Tiempo máximo para responder a una oferta de lista de espera.",
    )
    developer_commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        verbose_name="Comisión del desarrollador (%)",
        help_text="Porcentaje reservado para el desarrollador. Solo puede mantenerse o incrementarse.",
    )
    developer_payout_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("200000.00"),
        verbose_name="Umbral de pago al desarrollador",
        help_text="Saldo mínimo acumulado antes de intentar una dispersión al desarrollador.",
    )
    developer_in_default = models.BooleanField(
        default=False,
        verbose_name="Desarrollador en mora",
        help_text="Indica si el sistema adeuda pagos al desarrollador.",
    )
    developer_default_since = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Inicio de mora con el desarrollador",
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
        if self.vip_monthly_price is not None and self.vip_monthly_price < 0:
            errors["vip_monthly_price"] = "Debe ser un valor positivo."
        if self.advance_expiration_minutes < 1:
            errors["advance_expiration_minutes"] = "Debe ser al menos 1 minuto."
        if self.credit_expiration_days < 1:
            errors["credit_expiration_days"] = "Debe ser al menos 1 día."
        if self.return_window_days < 0:
            errors["return_window_days"] = "No puede ser negativo."
        if self.loyalty_months_required < 1:
            errors["loyalty_months_required"] = "Debe ser al menos 1."
        if self.waitlist_ttl_minutes < 5:
            errors["waitlist_ttl_minutes"] = "Debe ser al menos 5 minutos."
        commission = self.developer_commission_percentage
        if commission is None or commission <= 0:
            errors["developer_commission_percentage"] = "El porcentaje de la comisión debe ser mayor a cero."
        else:
            previous_value = None
            if self.pk:
                previous_value = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("developer_commission_percentage", flat=True)
                    .first()
                )
            if previous_value is not None and commission < previous_value:
                errors["developer_commission_percentage"] = "No se permite disminuir la comisión del desarrollador."
        threshold = self.developer_payout_threshold
        if threshold is None or threshold <= 0:
            errors["developer_payout_threshold"] = "El umbral de pago debe ser mayor que cero."

        # Validar timezone
        if self.timezone_display:
            try:
                ZoneInfo(self.timezone_display)
            except ZoneInfoNotFoundError:
                errors["timezone_display"] = f"Timezone inválido: {self.timezone_display}"

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Forzamos UUID singleton
        self.pk = self.id = GLOBAL_SETTINGS_SINGLETON_UUID

        # Log cambios importantes
        if self.pk:
            try:
                old = GlobalSettings.objects.get(pk=self.pk)
                changes = []
                for field in ['advance_payment_percentage', 'low_supervision_capacity',
                             'developer_commission_percentage']:
                    old_val = getattr(old, field)
                    new_val = getattr(self, field)
                    if old_val != new_val:
                        changes.append(f"{field}: {old_val} -> {new_val}")

                if changes:
                    logger.warning(
                        "GlobalSettings modificado: %s",
                        ", ".join(changes)
                    )
            except GlobalSettings.DoesNotExist:
                pass

        self.full_clean()
        super().save(*args, **kwargs)
        # Invalida/actualiza caché después de guardar
        cache.set(GLOBAL_SETTINGS_CACHE_KEY, self, timeout=None)

    @classmethod
    def load(cls) -> "GlobalSettings":
        """
        Obtiene la instancia desde caché o DB, creándola si no existe.
        Usa select_for_update para prevenir race conditions.
        """
        cached = cache.get(GLOBAL_SETTINGS_CACHE_KEY)
        if cached is not None:
            return cached

        # Usar select_for_update con get_or_create para evitar race conditions
        with transaction.atomic():
            try:
                obj = cls.objects.select_for_update().get(id=GLOBAL_SETTINGS_SINGLETON_UUID)
            except cls.DoesNotExist:
                obj = cls.objects.create(id=GLOBAL_SETTINGS_SINGLETON_UUID)

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
