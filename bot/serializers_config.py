"""
Serializers para configuración del Bot.
"""
from rest_framework import serializers
from .models.config import BotConfiguration


class BotConfigurationSerializer(serializers.ModelSerializer):
    """
    Serializer de solo lectura para BotConfiguration.
    
    Expone todos los campos de configuración del bot.
    """
    
    class Meta:
        model = BotConfiguration
        fields = [
            'id',
            'site_name',
            'booking_url',
            'admin_phone',
            'system_prompt_template',
            'api_input_price_per_1k',
            'api_output_price_per_1k',
            'daily_cost_alert_threshold',
            'avg_tokens_alert_threshold',
            'enable_critical_alerts',
            'enable_auto_block',
            'auto_block_critical_threshold',
            'auto_block_analysis_period_hours',
            'is_active',
        ]
        read_only_fields = ['id']


class BotConfigurationUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para actualizar BotConfiguration.
    
    Permite modificar todos los campos excepto el ID.
    Incluye validaciones del modelo (clean()).
    """
    
    class Meta:
        model = BotConfiguration
        fields = [
            'site_name',
            'booking_url',
            'admin_phone',
            'system_prompt_template',
            'api_input_price_per_1k',
            'api_output_price_per_1k',
            'daily_cost_alert_threshold',
            'avg_tokens_alert_threshold',
            'enable_critical_alerts',
            'enable_auto_block',
            'auto_block_critical_threshold',
            'auto_block_analysis_period_hours',
            'is_active',
        ]
    
    def validate_system_prompt_template(self, value):
        """
        Validación adicional del prompt para asegurar variables críticas.
        """
        required_vars = [
            'user_message',
            'services_context',
            'products_context',
            'booking_url',
        ]
        
        missing_vars = []
        for var in required_vars:
            if f'{{{{{var}}}}}' not in value and f'{{{{ {var} }}}}' not in value:
                missing_vars.append(var)
        
        if missing_vars:
            raise serializers.ValidationError(
                f"El prompt debe contener las variables: {', '.join([f'{{{{{v}}}}}' for v in missing_vars])}"
            )
        
        return value
    
    def update(self, instance, validated_data):
        """
        Actualiza la configuración del bot.
        El método save() del modelo invalida el caché automáticamente.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # El modelo ejecuta full_clean() en save()
        instance.save()
        return instance
