import uuid
from decimal import Decimal
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


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    use_in_migrations = True

    def __init__(self, *args, include_deleted=False, **kwargs):
        self.include_deleted = include_deleted
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        if not self.include_deleted:
            qs = qs.filter(is_deleted=False)
        return qs

    def hard_delete(self):
        return self.get_queryset().hard_delete()


class SoftDeleteModel(BaseModel):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager(include_deleted=True)

    class Meta(BaseModel.Meta):
        abstract = True
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def delete(self, using=None, keep_parents=False):
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        if not self.is_deleted:
            return
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class AuditLog(BaseModel):
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


class IdempotencyKey(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        COMPLETED = "COMPLETED", "Completado"

    key = models.CharField(max_length=255, unique=True)
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
