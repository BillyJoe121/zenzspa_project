from django.db import models
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import re

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
        default=1.0,
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


class BotConversationLog(models.Model):
    """
    CORRECCIÓN CRÍTICA: Modelo de auditoría para conversaciones del bot.
    Permite investigar problemas, mejorar el prompt, y detectar patrones de abuso.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bot_conversations'
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
            models.Index(fields=['was_blocked', '-created_at']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
