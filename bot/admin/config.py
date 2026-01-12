from django.contrib import admin

from ..models import BotConfiguration


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
        ('Alertas de Seguridad', {
            'fields': ('enable_critical_alerts',),
            'description': 'Habilitar notificaciones por email cuando se detecten actividades críticas.'
        }),
        ('Auto-Bloqueo', {
            'fields': ('enable_auto_block', 'auto_block_critical_threshold', 'auto_block_analysis_period_hours'),
            'description': 'Configurar bloqueo automático de IPs con comportamiento abusivo. '
                          'Una IP será bloqueada automáticamente si alcanza el umbral de actividades '
                          'críticas en el período especificado.'
        }),
    )

    # SEGURIDAD: Truco para impedir que creen más de una configuración (Singleton)
    def has_add_permission(self, request):
        """
        Solo ADMIN y SUPERUSER pueden agregar configuración.
        Además, solo se permite una configuración (Singleton).
        """
        from users.models import CustomUser
        has_role_permission = (
            request.user.is_superuser or 
            request.user.role == CustomUser.Role.ADMIN
        )
        return has_role_permission and not BotConfiguration.objects.exists()
    
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

