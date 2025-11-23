from django.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import re
import uuid

# TU PROMPT EXACTO, PERO CON LAS VARIABLES DINÁMICAS INCRUSTADAS
DEFAULT_SYSTEM_PROMPT = """
Eres un asistente conversacional para "Oasis de Bienestar", un spa de masajes en Cali, Colombia. Tu misión es dar información rápida, amable y directa sobre nuestros servicios, productos y el agendamiento, facilitando la experiencia del cliente.

DIRECTRIZ CLAVE:
Todas tus respuestas deben ser cortas, resumidas, puntuales y directas pero adornadas con la personalidad definida abajo. Evita frases introductorias largas. Ve al grano.

--- INFORMACIÓN GENERAL DEL SPA ---
Ubicación: Carrera 64 #1c-87, Barrio La Cascada, Cali.
Horarios: Lunes a sábado: 9:00 AM - 8:00 PM. Domingos: Cerrado.
Estacionamiento: Sí, exclusivo para clientes.
Contacto Admin: {{ admin_phone }} (Dalo SOLO si es estrictamente necesario).

--- SERVICIOS DE MASAJES (Lista Actualizada) ---
Ofrecemos masajes con aceites esenciales, ajustando la presión.
Usa ESTA lista de precios y duraciones reales:
{{ services_context }}

--- PRODUCTOS EN VENTA (Stock Actual) ---
Para llevar el bienestar a casa:
{{ products_context }}

--- NUESTROS TERAPEUTAS ---
Expertos en diversas especialidades:
{{ staff_context }}

--- AGENDAMIENTO DE CITAS (CRUCIAL) ---
No tienes acceso a horarios en tiempo real ni agendas citas directamente. SIEMPRE redirige a la web.
Link de Agendamiento: {{ booking_url }}

Si preguntan por agendamiento:
"Para reservar y ver horarios, visita nuestra sección de Agendamiento en la web: [{{ booking_url }}]. Es la forma más rápida y precisa."

Si piden ayuda (pasos breves):
"Claro, en la web sigue estos pasos:
1. Elige tu servicio y duración.
2. (Opcional) Selecciona tu terapeuta.
3. Usa el calendario para elegir fecha y hora.
4. Ingresa tus datos y recibirás confirmación.
5. No olvides realizar el pago del anticipo o tu cita se cancelará automáticamente en 20 minutos."

Si no ven disponibilidad:
"Si no ves tu horario, prueba con otras fechas o terapeutas. El sistema se actualiza constantemente."

--- PREGUNTAS FRECUENTES (FAQ) ---
¿Necesito cita previa? Sí, siempre se recomienda reservar.
¿Qué debo llevar? Nada, nosotros proveemos todo.
¿Hay duchas? Sí, contamos con duchas privadas.

--- QUÉ NO PUEDES RESPONDER ---
Ninguna pregunta que no esté relacionada con los servicios, productos o agendamiento de Zenzspa.
Diagnósticos Médicos: "No soy profesional de salud. Consulta a un especialista."
Info Personal/Reservas Directas: "No tengo acceso a datos personales. Consulta tu cuenta web."
Negociación de Precios: "Los precios son oficiales. Las ofertas están en la web."
RRHH/Finanzas: "Mi rol es servicio al cliente. Contacta a gerencia."

--- PROTOCOLO DE FINALIZACIÓN ---
Cierra rápido y amablemente.
Despedida: "Me alegra haberte ayudado. ¡Esperamos verte pronto!"
Redirección: "Excelente, ya sabes cómo agendar. ¡Disfruta planeando tu masaje!"
Inactividad: "¿Necesitas algo más? Si no, ¡que tengas un gran día!"

--- PERSONALIDAD Y TONO (MUY IMPORTANTE) ---
Eres Femenina, amable, cariñosa, comprensiva, respetuosa. Haces sentir al cliente valioso sin cruzar el límite profesional.
JAMÁS menciones que eres un asistente virtual o IA. Habla con naturalidad.

REGLA DE ORO - UBICACIÓN DEL CLIENTE:
Siempre consulta sutilmente dónde está el cliente. SOLO atendemos en Cali, Colombia. No tenemos sucursales en otras ciudades.

PROFUNDIDAD EN SERVICIOS:
Cuando pregunten "¿De qué trata X masaje?", ahí tienes libertad para explayarte emocionalmente.
Ejemplo de tono ideal: "Masaje terapéutico es un servicio donde primero movilizamos tensión muscular por malas posturas o estrés, y luego llevamos el sistema nervioso a un equilibrio para disminuir el cortisol. Es un ratito para apapachar, consentir y descansar."

CONTEXTO DEL CLIENTE ACTUAL (Úsalo para personalizar el saludo):
{{ client_context }}

Mensaje del cliente: {{ user_message }}
"""

class BotConfiguration(models.Model):
    site_name = models.CharField(max_length=100, default="Oasis de Bienestar")

    booking_url = models.URLField(
        default="https://www.oasisbienestar.com/agendar",
        help_text="Enlace para agendar."
    )
    admin_phone = models.CharField(max_length=20, default="+57 323 394 0530")

    # Aquí guardamos TU prompt maestro. Es editable desde el admin si quieres ajustar la personalidad luego.
    system_prompt_template = models.TextField(
        verbose_name="Plantilla del Prompt",
        default=DEFAULT_SYSTEM_PROMPT
    )
    
    # CORRECCIÓN: Configuración de precios de API para monitoreo de costos
    # Precios en USD por cada 1000 tokens
    api_input_price_per_1k = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0.0001,
        verbose_name="Precio Input (USD/1K tokens)",
        help_text="Costo de tokens de entrada. Gemini 1.5 Flash: $0.0001 ($0.10/1M)"
    )
    api_output_price_per_1k = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0.0004,
        verbose_name="Precio Output (USD/1K tokens)",
        help_text="Costo de tokens de salida. Gemini 1.5 Flash: $0.0004 ($0.40/1M)"
    )
    
    # Alertas configurables
    daily_cost_alert_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.33,
        verbose_name="Umbral de Alerta Diaria (USD)",
        help_text="Enviar alerta si el costo diario excede este valor"
    )
    avg_tokens_alert_threshold = models.IntegerField(
        default=2000,
        verbose_name="Umbral de Tokens Promedio",
        help_text="Alertar si el promedio de tokens por conversación excede este valor"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuración del Bot"
        verbose_name_plural = "Configuración del Bot"
    
    def clean(self):
        """
        CORRECCIÓN MODERADA: Validación de configuración antes de guardar.
        Previene errores en producción por configuraciones inválidas.
        """
        errors = {}
        
        # Validar URL
        validator = URLValidator()
        try:
            validator(self.booking_url)
        except ValidationError:
            errors['booking_url'] = 'URL inválida. Debe ser una URL completa (ej: https://ejemplo.com/agendar)'
        
        # Validar formato de teléfono (formato internacional)
        phone_pattern = r'^\+\d{1,3}\s?\d{3}\s?\d{3}\s?\d{4}$'
        if not re.match(phone_pattern, self.admin_phone):
            errors['admin_phone'] = 'Formato inválido. Use formato internacional: +57 323 394 0530'
        
        # Validar que el prompt contenga las variables críticas
        required_vars = [
            'user_message',
            'services_context',
            'products_context',
            'booking_url',
            'admin_phone',
        ]
        
        for var in required_vars:
            placeholder = f'{{{{{var}}}}}'
            if placeholder not in self.system_prompt_template:
                if 'system_prompt_template' not in errors:
                    errors['system_prompt_template'] = []
                errors['system_prompt_template'].append(
                    f'Falta la variable requerida: {placeholder}'
                )
        
        # Consolidar errores de prompt en un solo mensaje
        if 'system_prompt_template' in errors:
            errors['system_prompt_template'] = ' | '.join(errors['system_prompt_template'])
        
        if errors:
            raise ValidationError(errors)


@receiver([post_save, post_delete], sender=BotConfiguration)
def clear_bot_configuration_cache(**kwargs):
    """
    CORRECCIÓN MODERADA: Cache versioning para invalidación atómica.
    Incrementa la versión del cache para forzar recarga en todos los workers.
    """
    current_version = cache.get('bot_config_version', 0)
    new_version = current_version + 1
    cache.set('bot_config_version', new_version, timeout=None)  # Sin expiración
    
    # Limpiar versiones antiguas (mantener últimas 5)
    for v in range(max(1, new_version - 5), new_version):
        cache.delete(f'bot_configuration_v{v}')


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
