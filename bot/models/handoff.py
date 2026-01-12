from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .conversation import AnonymousUser, BotConversationLog


class HumanHandoffRequest(models.Model):
    """
    Modelo para solicitudes de escalamiento a atención humana.
    Permite que staff/admin respondan a clientes que piden hablar con una persona.
    """

    class EscalationReason(models.TextChoices):
        EXPLICIT_REQUEST = 'EXPLICIT_REQUEST', 'Solicitud Explícita del Cliente'
        FRUSTRATION_DETECTED = 'FRUSTRATION_DETECTED', 'Frustración Detectada'
        HIGH_VALUE_CLIENT = 'HIGH_VALUE_CLIENT', 'Cliente de Alto Valor'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        ASSIGNED = 'ASSIGNED', 'Asignado'
        IN_PROGRESS = 'IN_PROGRESS', 'En Progreso'
        RESOLVED = 'RESOLVED', 'Resuelto'
        CANCELLED = 'CANCELLED', 'Cancelado'
        EXPIRED = 'EXPIRED', 'Expirado por Tiempo'

    # Usuario (registrado o anónimo)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoff_requests',
        null=True,
        blank=True,
        help_text="Usuario registrado (null si es anónimo)"
    )
    anonymous_user = models.ForeignKey(
        AnonymousUser,
        on_delete=models.CASCADE,
        related_name='handoff_requests',
        null=True,
        blank=True,
        help_text="Usuario anónimo (null si es registrado)"
    )

    # Información del escalamiento
    conversation_log = models.ForeignKey(
        BotConversationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handoff_requests',
        help_text="Log de la conversación que generó el escalamiento"
    )

    client_score = models.IntegerField(
        default=0,
        help_text="Score del cliente (0-100) basado en valor potencial"
    )

    escalation_reason = models.CharField(
        max_length=30,
        choices=EscalationReason.choices,
        help_text="Razón del escalamiento"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Estado actual de la solicitud"
    )

    # Asignación
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_handoffs',
        help_text="Staff member asignado"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Contexto de la conversación (JSON)
    conversation_context = models.JSONField(
        default=dict,
        help_text="Resumen de la conversación hasta el momento del escalamiento"
    )

    # Intereses del cliente (JSON)
    client_interests = models.JSONField(
        default=dict,
        help_text="Servicios/productos consultados, presupuesto mencionado, etc."
    )

    # Notas internas
    internal_notes = models.TextField(
        blank=True,
        default="",
        help_text="Notas internas del staff sobre el cliente"
    )

    class Meta:
        verbose_name = "Solicitud de Atención Humana"
        verbose_name_plural = "Solicitudes de Atención Humana"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['anonymous_user', '-created_at']),
            models.Index(fields=['-client_score']),
        ]

    def clean(self):
        """Validación: debe tener usuario O usuario anónimo, pero no ambos"""
        if self.user and self.anonymous_user:
            raise ValidationError("Una solicitud no puede tener usuario y usuario anónimo simultáneamente")
        if not self.user and not self.anonymous_user:
            raise ValidationError("Una solicitud debe tener usuario o usuario anónimo")

    @property
    def client_identifier(self):
        """Identificador del cliente"""
        if self.user:
            return self.user.phone_number
        elif self.anonymous_user:
            return self.anonymous_user.display_name
        return "Desconocido"

    @property
    def client_contact_info(self):
        """Información de contacto del cliente"""
        if self.user:
            return {
                'name': self.user.get_full_name(),
                'phone': self.user.phone_number,
                'email': self.user.email,
            }
        elif self.anonymous_user:
            return {
                'name': self.anonymous_user.name or 'Visitante',
                'phone': self.anonymous_user.phone_number or 'No proporcionado',
                'email': self.anonymous_user.email or 'No proporcionado',
            }
        return {}

    @property
    def is_active(self):
        """Verifica si la solicitud está activa (no resuelta ni cancelada)"""
        return self.status not in [self.Status.RESOLVED, self.Status.CANCELLED]

    @property
    def response_time(self):
        """Tiempo de respuesta (asignación) en minutos"""
        if self.assigned_at:
            delta = self.assigned_at - self.created_at
            return int(delta.total_seconds() / 60)
        return None

    @property
    def resolution_time(self):
        """Tiempo total de resolución en minutos"""
        if self.resolved_at:
            delta = self.resolved_at - self.created_at
            return int(delta.total_seconds() / 60)
        return None

    def __str__(self):
        return f"{self.client_identifier} - {self.get_escalation_reason_display()} ({self.status})"


class HumanMessage(models.Model):
    """
    Modelo para mensajes en la conversación entre staff y cliente.
    Permite chat bidireccional después del escalamiento.
    """
    handoff_request = models.ForeignKey(
        HumanHandoffRequest,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text="Solicitud de handoff asociada"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages',
        help_text="Usuario que envía el mensaje (staff o cliente registrado)"
    )

    # Para mensajes de clientes anónimos
    from_anonymous = models.BooleanField(
        default=False,
        help_text="True si el mensaje es de un cliente anónimo"
    )

    is_from_staff = models.BooleanField(
        default=False,
        help_text="True si el mensaje es del staff, False si es del cliente"
    )

    message = models.TextField(help_text="Contenido del mensaje")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Momento en que el mensaje fue leído"
    )

    # Adjuntos (opcional para futuro)
    attachments = models.JSONField(
        default=list,
        blank=True,
        help_text="URLs de archivos adjuntos (imágenes, documentos, etc.)"
    )

    class Meta:
        verbose_name = "Mensaje Humano"
        verbose_name_plural = "Mensajes Humanos"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['handoff_request', 'created_at']),
            models.Index(fields=['is_from_staff', 'created_at']),
            models.Index(fields=['read_at']),
        ]

    @property
    def sender_name(self):
        """Nombre del remitente"""
        if self.is_from_staff and self.sender:
            return self.sender.get_full_name() or "Staff"
        elif self.from_anonymous:
            return self.handoff_request.anonymous_user.display_name if self.handoff_request.anonymous_user else "Visitante"
        elif self.sender:
            return self.sender.get_full_name()
        return "Desconocido"

    @property
    def is_unread(self):
        """Verifica si el mensaje no ha sido leído"""
        return self.read_at is None

    def mark_as_read(self):
        """Marca el mensaje como leído"""
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])

    def __str__(self):
        direction = "→ Cliente" if self.is_from_staff else "← Cliente"
        return f"{self.handoff_request.client_identifier} {direction}: {self.message[:50]}..."
