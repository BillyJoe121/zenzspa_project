import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from bot.prompts import DEFAULT_SYSTEM_PROMPT


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
