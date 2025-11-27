from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .conversation import AnonymousUser, BotConversationLog


class IPBlocklist(models.Model):
    """
    Modelo para bloquear IPs maliciosas o abusivas.
    Permite al admin bloquear completamente el acceso de una IP al bot.
    """
    class BlockReason(models.TextChoices):
        ABUSE = 'ABUSE', 'Abuso de Límites'
        MALICIOUS_CONTENT = 'MALICIOUS_CONTENT', 'Contenido Malicioso'
        SPAM = 'SPAM', 'Spam/Flooding'
        FRAUD = 'FRAUD', 'Fraude Detectado'
        MANUAL = 'MANUAL', 'Bloqueo Manual por Admin'

    ip_address = models.GenericIPAddressField(
        unique=True,
        help_text="IP bloqueada"
    )

    reason = models.CharField(
        max_length=30,
        choices=BlockReason.choices,
        help_text="Razón del bloqueo"
    )

    notes = models.TextField(
        blank=True,
        default="",
        help_text="Notas internas sobre el bloqueo"
    )

    # Quien bloqueó
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='blocked_ips',
        help_text="Admin que bloqueó la IP"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de expiración del bloqueo (null = permanente)"
    )

    # Estado
    is_active = models.BooleanField(
        default=True,
        help_text="Si el bloqueo está activo"
    )

    class Meta:
        verbose_name = "IP Bloqueada"
        verbose_name_plural = "IPs Bloqueadas"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ip_address', 'is_active']),
            models.Index(fields=['-created_at']),
        ]

    @property
    def is_expired(self):
        """Verifica si el bloqueo ha expirado"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_effective(self):
        """Verifica si el bloqueo está activo y no ha expirado"""
        return self.is_active and not self.is_expired

    def __str__(self):
        status = "Activo" if self.is_effective else "Inactivo"
        return f"{self.ip_address} - {self.get_reason_display()} ({status})"


class SuspiciousActivity(models.Model):
    """
    Modelo para rastrear actividad sospechosa de usuarios/IPs.
    Permite al admin ver un historial completo de comportamiento problemático.
    """
    class ActivityType(models.TextChoices):
        RATE_LIMIT_HIT = 'RATE_LIMIT_HIT', 'Límite de Velocidad Alcanzado'
        DAILY_LIMIT_HIT = 'DAILY_LIMIT_HIT', 'Límite Diario Alcanzado'
        REPETITIVE_MESSAGES = 'REPETITIVE_MESSAGES', 'Mensajes Repetitivos'
        JAILBREAK_ATTEMPT = 'JAILBREAK_ATTEMPT', 'Intento de Jailbreak'
        MALICIOUS_CONTENT = 'MALICIOUS_CONTENT', 'Contenido Malicioso'
        OFF_TOPIC_SPAM = 'OFF_TOPIC_SPAM', 'Spam Fuera de Tema'
        EXCESSIVE_TOKENS = 'EXCESSIVE_TOKENS', 'Uso Excesivo de Tokens'
        IP_ROTATION = 'IP_ROTATION', 'Rotación de IP Sospechosa'

    class SeverityLevel(models.IntegerChoices):
        LOW = 1, 'Baja'
        MEDIUM = 2, 'Media'
        HIGH = 3, 'Alta'
        CRITICAL = 4, 'Crítica'

    # Usuario (registrado o anónimo)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='suspicious_activities',
        null=True,
        blank=True,
        help_text="Usuario registrado (null si es anónimo)"
    )
    anonymous_user = models.ForeignKey(
        AnonymousUser,
        on_delete=models.CASCADE,
        related_name='suspicious_activities',
        null=True,
        blank=True,
        help_text="Usuario anónimo (null si es registrado)"
    )

    # IP asociada
    ip_address = models.GenericIPAddressField(
        help_text="IP desde donde se realizó la actividad sospechosa"
    )

    # Tipo de actividad sospechosa
    activity_type = models.CharField(
        max_length=30,
        choices=ActivityType.choices,
        help_text="Tipo de actividad sospechosa detectada"
    )

    # Severidad
    severity = models.IntegerField(
        choices=SeverityLevel.choices,
        default=SeverityLevel.MEDIUM,
        help_text="Nivel de severidad de la actividad"
    )

    # Detalles
    description = models.TextField(
        help_text="Descripción detallada de la actividad sospechosa"
    )

    # Contexto (JSON con datos adicionales)
    context = models.JSONField(
        default=dict,
        help_text="Contexto adicional: mensaje enviado, respuesta, metadata, etc."
    )

    # Referencia al log de conversación si existe
    conversation_log = models.ForeignKey(
        BotConversationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suspicious_activities',
        help_text="Log de conversación asociado"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    # Estado de revisión
    reviewed = models.BooleanField(
        default=False,
        help_text="Si un admin ya revisó esta actividad"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_suspicious_activities',
        help_text="Admin que revisó la actividad"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de revisión"
    )

    # Notas del admin
    admin_notes = models.TextField(
        blank=True,
        default="",
        help_text="Notas del admin sobre esta actividad"
    )

    class Meta:
        verbose_name = "Actividad Sospechosa"
        verbose_name_plural = "Actividades Sospechosas"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ip_address', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['anonymous_user', '-created_at']),
            models.Index(fields=['activity_type', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['reviewed', '-created_at']),
        ]

    def clean(self):
        """Validación: debe tener usuario O usuario anónimo, pero no ambos"""
        if self.user and self.anonymous_user:
            raise ValidationError("Una actividad no puede tener usuario y usuario anónimo simultáneamente")
        if not self.user and not self.anonymous_user:
            raise ValidationError("Una actividad debe tener usuario o usuario anónimo")

    @property
    def participant_identifier(self):
        """Identificador del participante"""
        if self.user:
            return self.user.phone_number
        elif self.anonymous_user:
            return self.anonymous_user.display_name
        return "Desconocido"

    @property
    def severity_color(self):
        """Color para mostrar en el admin"""
        colors = {
            self.SeverityLevel.LOW: 'green',
            self.SeverityLevel.MEDIUM: 'orange',
            self.SeverityLevel.HIGH: 'red',
            self.SeverityLevel.CRITICAL: 'darkred',
        }
        return colors.get(self.severity, 'gray')

    def mark_as_reviewed(self, admin_user, notes=""):
        """Marca la actividad como revisada"""
        self.reviewed = True
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        if notes:
            self.admin_notes = notes
        self.save()

    def __str__(self):
        return f"{self.participant_identifier} - {self.get_activity_type_display()} ({self.get_severity_display()})"

