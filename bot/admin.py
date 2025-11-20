from django.contrib import admin
from .models import BotConfiguration, BotConversationLog


@admin.register(BotConfiguration)
class BotConfigurationAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'is_active', 'booking_url', 'api_input_price_per_1k', 'api_output_price_per_1k')
    
    fieldsets = (
        ('Información General', {
            'fields': ('site_name', 'booking_url', 'admin_phone', 'is_active')
        }),
        ('Configuración del Prompt', {
            'fields': ('system_prompt_template',),
            'classes': ('collapse',),
        }),
        ('Precios de API (Monitoreo de Costos)', {
            'fields': ('api_input_price_per_1k', 'api_output_price_per_1k'),
            'description': 'Configure los precios actuales de la API de Gemini. '
                          'Estos valores se usan para calcular costos en los reportes diarios.'
        }),
        ('Umbrales de Alertas', {
            'fields': ('daily_cost_alert_threshold', 'avg_tokens_alert_threshold'),
            'description': 'Configure cuándo se deben enviar alertas de costos y eficiencia.'
        }),
    )

    # SEGURIDAD: Truco para impedir que creen más de una configuración (Singleton)
    def has_add_permission(self, request):
        return not BotConfiguration.objects.exists()
    
    # SEGURIDAD CRÍTICA: Solo ADMIN y SUPERUSER pueden modificar la configuración del bot
    def has_change_permission(self, request, obj=None):
        """
        Solo usuarios con role=ADMIN o is_superuser=True pueden editar.
        STAFF NO tiene acceso a modificar configuración sensible.
        """
        from users.models import CustomUser
        return (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )
    
    # SEGURIDAD CRÍTICA: Solo ADMIN y SUPERUSER pueden eliminar la configuración
    def has_delete_permission(self, request, obj=None):
        """Solo ADMIN y SUPERUSER pueden eliminar configuración."""
        from users.models import CustomUser
        return (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )
    
    # SEGURIDAD: Solo ADMIN y SUPERUSER pueden ver la configuración
    def has_view_permission(self, request, obj=None):
        """
        Solo ADMIN y SUPERUSER pueden ver la configuración del bot.
        STAFF NO tiene acceso a información sensible como precios de API.
        """
        from users.models import CustomUser
        return (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )


@admin.register(BotConversationLog)
class BotConversationLogAdmin(admin.ModelAdmin):
    """Admin para auditar conversaciones del bot"""
    list_display = ('user', 'created_at', 'was_blocked', 'block_reason', 'latency_ms', 'tokens_used')
    list_filter = ('was_blocked', 'block_reason', 'created_at')
    search_fields = ('user__phone_number', 'message', 'response')
    readonly_fields = ('user', 'message', 'response', 'response_meta', 
                      'was_blocked', 'block_reason', 'latency_ms', 'tokens_used', 'created_at')
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        # No permitir crear logs manualmente
        return False
    
    def has_change_permission(self, request, obj=None):
        # Nadie puede editar logs (readonly)
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Solo ADMIN y superusers pueden borrar logs
        from users.models import CustomUser
        return (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )
    
    # SEGURIDAD: Solo ADMIN y SUPERUSER pueden ver logs de conversaciones
    def has_view_permission(self, request, obj=None):
        """
        Solo ADMIN y SUPERUSER pueden ver logs de conversaciones.
        STAFF NO tiene acceso a conversaciones privadas de clientes.
        """
        from users.models import CustomUser
        return (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )
