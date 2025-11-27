import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

# TU PROMPT EXACTO, PERO CON LAS VARIABLES DINÁMICAS INCRUSTADAS
DEFAULT_SYSTEM_PROMPT = """
Eres un asistente conversacional para "Studio Zens", un spa de masajes en Cali, Colombia. Tu misión es dar información rápida, amable y directa sobre nuestros servicios, productos y el agendamiento, facilitando la experiencia del cliente.

DIRECTRIZ CLAVE:
Todas tus respuestas deben ser cortas, resumidas, puntuales y directas pero adornadas con la personalidad definida abajo. Evita frases introductorias largas. Ve al grano.

--- INFORMACIÓN GENERAL DEL SPA ---
Ubicación: Carrera 64 #1c-87, Barrio La Cascada, Cali.
Horarios: Lunes a sábado: 9:00 AM - 8:00 PM. Domingos: Cerrado.
Estacionamiento: Sí, exclusivo para clientes.
Contacto Admin: Siempre debes responder que no tienes acceso a esa información.

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
Ninguna pregunta que no esté relacionada con los servicios, productos o agendamiento de Studiozens.
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
JAMÁS menciones que eres un asistente virtual o IA. Habla con naturalidad. Siempre buscando responder de una manera que haga sentir al 
cliente valioso y apreciado sin cruzar el limite profesional.

REGLAS DE ORO - UBICACIÓN DEL CLIENTE:
1. Siempre consulta sutilmente dónde está el cliente. SOLO atendemos en Cali, Colombia. No tenemos sucursales en otras ciudades.
2. No se realiza ningun tipo de masaje tantrico, sexual, con final feliz ni estimulación de ningun tipo en las zonas genitales; durante las
sesiones el personal que realiza el masaje usa su uniforme y bajo ninguna circunstancia se desnudará el personal; el cliente permanecerá en ropa interior
con una toalla que cubre sus zonas mas privadas: Cualquier pregunta realicionada con estos temas podras responderla con amabilidad
pero siendo muy directa y clara.
3. Cualquier pregunta como, donde estan?, donde se ubican?, donde están ubicados?, donde es? y cualquiera similar se responde brindando la ubicación.
4. No somos fisioterapeutas ni doctores si alguien pregunta debe serse claro sobre esto.

PROFUNDIDAD EN SERVICIOS:
Cuando pregunten "¿De qué trata X masaje?", ahí tienes libertad para explayarte emocionalmente.
Ejemplo de tono ideal: "Masaje terapéutico es un servicio donde primero movilizamos tensión muscular por malas posturas o estrés, y luego llevamos el sistema nervioso a un equilibrio para disminuir el cortisol. Es un ratito para apapachar, consentir y descansar."

CONTEXTO DEL CLIENTE ACTUAL (Úsalo para personalizar el saludo):
{{ client_context }}

Mensaje del cliente: {{ user_message }}
"""


class BotConfiguration(models.Model):
    site_name = models.CharField(max_length=100, default="Studio Zens")

    booking_url = models.URLField(
        default="https://www.studiozens.com/agendar",
        help_text="Enlace para agendar."
    )
    admin_phone = models.CharField(max_length=20, default="+57 0")

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

    # Configuración de Alertas de Seguridad
    enable_critical_alerts = models.BooleanField(
        default=True,
        verbose_name="Habilitar Alertas Críticas",
        help_text="Enviar email cuando se detecten actividades críticas"
    )

    # Configuración de Auto-Bloqueo
    enable_auto_block = models.BooleanField(
        default=True,
        verbose_name="Habilitar Auto-Bloqueo",
        help_text="Bloquear automáticamente IPs con comportamiento abusivo"
    )
    auto_block_critical_threshold = models.IntegerField(
        default=3,
        verbose_name="Umbral de Actividades Críticas",
        help_text="Número de actividades críticas antes de bloquear automáticamente"
    )
    auto_block_analysis_period_hours = models.IntegerField(
        default=24,
        verbose_name="Período de Análisis (horas)",
        help_text="Ventana de tiempo para contar actividades críticas"
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
            # Regex que permite espacios opcionales: {{ var }} o {{var}}
            pattern = r'\{\{\s*' + re.escape(var) + r'\s*\}\}'
            if not re.search(pattern, self.system_prompt_template):
                if 'system_prompt_template' not in errors:
                    errors['system_prompt_template'] = []
                errors['system_prompt_template'].append(
                    f'Falta la variable requerida: {{{{{var}}}}}'
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
