import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AnonymousUser(models.Model):
    """
    Modelo para trackear usuarios anónimos que interactúan con el bot.
    Permite dar soporte a usuarios no registrados y potencialmente convertirlos.
    """
    session_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        help_text="ID único de sesión para trackear usuario anónimo"
    )
    ip_address = models.GenericIPAddressField(
        help_text="Dirección IP del usuario anónimo"
    )

    # Información opcional que puede recopilar el bot
    name = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True, default="")

    # Control de tiempo
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        help_text="Fecha de expiración de la sesión (30 días)"
    )

    # Conversión
    converted_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_anonymous_users',
        help_text="Usuario registrado al que se convirtió este anónimo"
    )

    class Meta:
        verbose_name = "Usuario Anónimo"
        verbose_name_plural = "Usuarios Anónimos"
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['ip_address', '-created_at']),
            models.Index(fields=['-last_activity']),
        ]

    def save(self, *args, **kwargs):
        # Establecer fecha de expiración si es nuevo
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.name:
            return f"Anónimo: {self.name} ({self.session_id})"
        return f"Anónimo: {self.session_id}"

    @property
    def is_expired(self):
        """Verifica si la sesión ha expirado"""
        return timezone.now() > self.expires_at

    @property
    def display_name(self):
        """Nombre para mostrar en la interfaz"""
        return self.name if self.name else f"Visitante {str(self.session_id)[:8]}"


class BotConversationLog(models.Model):
    """
    CORRECCIÓN CRÍTICA: Modelo de auditoría para conversaciones del bot.
    Permite investigar problemas, mejorar el prompt, y detectar patrones de abuso.
    Soporta tanto usuarios registrados como anónimos.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bot_conversations',
        null=True,
        blank=True,
        help_text="Usuario registrado (null si es anónimo)"
    )
    anonymous_user = models.ForeignKey(
        AnonymousUser,
        on_delete=models.CASCADE,
        related_name='bot_conversations',
        null=True,
        blank=True,
        help_text="Usuario anónimo (null si es registrado)"
    )

    message = models.TextField(help_text="Mensaje enviado por el usuario")
    response = models.TextField(help_text="Respuesta generada por el bot")
    response_meta = models.JSONField(
        default=dict,
        help_text="Metadata de la respuesta (source, tokens, etc.)"
    )

    # Flags de seguridad
    was_blocked = models.BooleanField(
        default=False,
        help_text="Si la respuesta fue bloqueada por seguridad"
    )
    block_reason = models.CharField(
        max_length=50,
        blank=True,
        help_text="Razón del bloqueo (security_guardrail, jailbreak, etc.)"
    )

    # Métricas
    latency_ms = models.IntegerField(
        default=0,
        help_text="Latencia de la respuesta en milisegundos"
    )

    # CORRECCIÓN CRÍTICA: Tracking de tokens para monitoreo de costos
    tokens_used = models.IntegerField(
        default=0,
        help_text="Tokens consumidos en esta conversación (prompt + completion)"
    )

    # AUDITORÍA: Tracking de IP para detección de fraude
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP del cliente para auditoría de fraude y análisis de patrones"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Conversación"
        verbose_name_plural = "Logs de Conversaciones"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['anonymous_user', '-created_at']),
            models.Index(fields=['was_blocked', '-created_at']),
            models.Index(fields=['-created_at']),
        ]

    def clean(self):
        """Validación: debe tener usuario O usuario anónimo, pero no ambos"""
        if self.user and self.anonymous_user:
            raise ValidationError("Una conversación no puede tener usuario y usuario anónimo simultáneamente")
        if not self.user and not self.anonymous_user:
            raise ValidationError("Una conversación debe tener usuario o usuario anónimo")

    @property
    def participant_identifier(self):
        """Identificador del participante (teléfono o nombre anónimo)"""
        if self.user:
            return self.user.phone_number
        elif self.anonymous_user:
            return self.anonymous_user.display_name
        return "Desconocido"

    def __str__(self):
        return f"{self.participant_identifier} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

