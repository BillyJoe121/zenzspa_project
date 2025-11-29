import re


from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.conf import settings
from cryptography.fernet import Fernet
from fernet_fields import EncryptedTextField

from core.models import BaseModel


class CancellationStreak(BaseModel):
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='cancellation_streaks'
    )
    date = models.DateField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True)
    
    class Meta:
        verbose_name = "Racha de Cancelación"
        verbose_name_plural = "Rachas de Cancelación"
        ordering = ['-created_at']




class CustomUserManager(BaseUserManager):
    def make_random_password(self, length=10, allowed_chars=None):
        return super().make_random_password(length=length, allowed_chars=allowed_chars)
    def create_user(self, phone_number, email=None, first_name="", password=None, **extra_fields):
        if not phone_number:
            raise ValueError('El número de teléfono es obligatorio.')

        email = self.normalize_email(email) if email else None
        user = self.model(
            phone_number=phone_number,
            email=email,
            first_name=first_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, first_name, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', self.model.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(phone_number, email, first_name, password, **extra_fields)


PHONE_NUMBER_REGEX = RegexValidator(
    regex=r"^\+[1-9]\d{9,14}$",
    message="El número debe estar en formato internacional (+573157589548).",
)


class CustomUser(BaseModel, AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CLIENT = 'CLIENT', 'Cliente'
        VIP = 'VIP', 'Suscriptor VIP'
        STAFF = 'STAFF', 'Trabajador'
        ADMIN = 'ADMIN', 'Administrador'

    phone_number = models.CharField(
        max_length=15,
        unique=True,
        verbose_name='Número de Teléfono',
        validators=[PHONE_NUMBER_REGEX],
    )
    email = models.EmailField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Correo Electrónico')
    first_name = models.CharField(max_length=100, verbose_name='Nombre')
    last_name = models.CharField(
        max_length=100, blank=True, verbose_name='Apellido')

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CLIENT, verbose_name='Rol')
    vip_expires_at = models.DateField(
        null=True, blank=True, verbose_name="Fecha de Vencimiento VIP",
        help_text="Indica hasta qué fecha la membresía VIP del usuario está activa.")
    vip_active_since = models.DateField(
        null=True,
        blank=True,
        verbose_name="Inicio de actividad VIP",
        help_text="Fecha desde la cual el usuario mantiene la membresía VIP de forma ininterrumpida.",
    )
    vip_auto_renew = models.BooleanField(
        default=True,
        verbose_name="Renovación automática VIP",
        help_text="Indica si la suscripción VIP debe intentarse renovar automáticamente.",
    )
    vip_payment_token = EncryptedTextField(
        blank=True,
        null=True,
        verbose_name="Token de pago recurrente (Encriptado)",
        help_text="Token seguro para cobrar renovaciones automáticas. Encriptado con Fernet.",
    )
    vip_failed_payments = models.PositiveIntegerField(
        default=0,
        verbose_name="Reintentos fallidos VIP",
    )
    is_verified = models.BooleanField(
        default=False, verbose_name='Verificado por SMS')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    is_staff = models.BooleanField(
        default=False, verbose_name='Personal del Staff')

    is_persona_non_grata = models.BooleanField(
        default=False, verbose_name="Cliente No Grato")

    # --- INICIO DE LA MODIFICACIÓN ---
    # Se elimina 'profile_picture' y se añaden los campos requeridos.
    internal_notes = models.TextField(
        blank=True, null=True, verbose_name="Notas Internas (Staff/Admin)")
    internal_photo_url = models.URLField(
        max_length=512, blank=True, null=True, verbose_name="URL de Foto Interna (Staff/Admin)")
    
    # --- MEJORAS IMPLEMENTADAS ---
    email_verified = models.BooleanField(
        default=False, verbose_name="Email Verificado"
    )
    totp_secret = models.CharField(
        max_length=32, blank=True, null=True, verbose_name="Secreto TOTP (2FA App)"
    )
    is_deleted = models.BooleanField(
        default=False, verbose_name="Eliminado Suavemente"
    )
    # --- FIN MEJORAS ---
    # --- FIN DE LA MODIFICACIÓN ---
    cancellation_streak = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Historial de cancelaciones/reagendamientos (DEPRECATED)",
        help_text="DEPRECATED: Usar modelo CancellationStreak. Almacena eventos recientes para aplicar penalizaciones (3 strikes).",
    )

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['first_name']

    def __str__(self):
        return f"{self.first_name} ({self.phone_number})"

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role', 'is_active']),
            models.Index(fields=['is_persona_non_grata']),
            models.Index(fields=['vip_expires_at']),
        ]

    def clean(self):
        """
        Validaciones de dominio del modelo CustomUser.

        Verifica que los campos cumplan las reglas de negocio antes de guardar.
        """
        super().clean()
        if self.phone_number:
            digits = self.phone_number.replace("+", "")
            if not digits.isdigit() or len(digits) < 10 or len(digits) > 15:
                raise ValidationError(
                    {'phone_number': 'Número de teléfono inválido. Usa formato internacional (+573157589548).'}
                )


    @property
    def is_vip(self):
        """
        Indica si el usuario tiene rol VIP y la membresía no está expirada.
        """
        if self.role != self.Role.VIP:
            return False
        if not self.vip_expires_at:
            return True
        return self.vip_expires_at >= timezone.now().date()

    def get_full_name(self):
        """
        Devuelve el nombre completo, compatible con la API estándar de Django.
        """
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.first_name or self.phone_number

    def has_pending_final_payment(self):
        """
        Determina si el usuario tiene un pago final pendiente de completar.
        """
        from spa.models import Appointment, Payment  # Import local para evitar ciclos

        has_pending_appointment = Appointment.objects.filter(
            user=self,
            status=Appointment.AppointmentStatus.PAID,
        ).exists()

        has_pending_payment = Payment.objects.filter(
            user=self,
            payment_type=Payment.PaymentType.FINAL,
            status=Payment.PaymentStatus.PENDING,
        ).exists()

        return has_pending_appointment or has_pending_payment


class UserSession(BaseModel):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    refresh_token_jti = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sesión de Usuario"
        verbose_name_plural = "Sesiones de Usuarios"
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['last_activity']),
        ]

    def __str__(self):
        return f"Sesión {self.refresh_token_jti} para {self.user}"


class OTPAttempt(BaseModel):
    class AttemptType(models.TextChoices):
        REQUEST = 'REQUEST', 'Solicitud'
        VERIFY = 'VERIFY', 'Verificación'

    phone_number = models.CharField(max_length=20)
    attempt_type = models.CharField(max_length=8, choices=AttemptType.choices)
    is_successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Intento OTP"
        verbose_name_plural = "Intentos OTP"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone_number', 'created_at']),
            models.Index(fields=['attempt_type', 'is_successful']),
        ]

    def __str__(self):
        return f"{self.phone_number} ({self.attempt_type}) - {'OK' if self.is_successful else 'FAIL'}"


class BlockedPhoneNumber(BaseModel):
    phone_number = models.CharField(max_length=20, unique=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Teléfono bloqueado (CNG)"
        verbose_name_plural = "Teléfonos bloqueados (CNG)"

    def __str__(self):
        return f"Número bloqueado: {self.phone_number}"


class BlockedDevice(BaseModel):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='blocked_devices',
        null=True,
        blank=True
    )
    device_fingerprint = models.CharField(max_length=255, unique=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_blocked = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Dispositivo Bloqueado"
        verbose_name_plural = "Dispositivos Bloqueados"

    def __str__(self):
        return f"Device {self.device_fingerprint[:8]}... ({'Blocked' if self.is_blocked else 'Active'})"

