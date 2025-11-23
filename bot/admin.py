from django.contrib import admin
from .models import BotConfiguration, BotConversationLog, AnonymousUser


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


@admin.register(AnonymousUser)
class AnonymousUserAdmin(admin.ModelAdmin):
    """Admin para usuarios anónimos del bot"""
    list_display = ('display_name', 'session_id', 'ip_address', 'created_at', 'last_activity', 'is_expired_status', 'converted_status')
    list_filter = ('created_at', 'last_activity', 'expires_at')
    search_fields = ('session_id', 'ip_address', 'name', 'email', 'phone_number')
    readonly_fields = ('session_id', 'created_at', 'last_activity', 'expires_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Información de Sesión', {
            'fields': ('session_id', 'ip_address', 'created_at', 'last_activity', 'expires_at')
        }),
        ('Información Recopilada (Opcional)', {
            'fields': ('name', 'email', 'phone_number'),
            'description': 'Información que el bot puede recopilar durante la conversación.'
        }),
        ('Conversión', {
            'fields': ('converted_to_user',),
            'description': 'Usuario registrado al que se convirtió este visitante anónimo.'
        }),
    )

    def is_expired_status(self, obj):
        return obj.is_expired
    is_expired_status.boolean = True
    is_expired_status.short_description = 'Expirado'

    def converted_status(self, obj):
        return obj.converted_to_user is not None
    converted_status.boolean = True
    converted_status.short_description = 'Convertido'

    def has_add_permission(self, request):
        # No permitir crear usuarios anónimos manualmente
        return False

    def has_change_permission(self, request, obj=None):
        # Permitir editar solo para conversión o recopilación de info
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_delete_permission(self, request, obj=None):
        # Solo ADMIN y superusers pueden borrar usuarios anónimos
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_view_permission(self, request, obj=None):
        """ADMIN y STAFF pueden ver usuarios anónimos"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )


@admin.register(BotConversationLog)
class BotConversationLogAdmin(admin.ModelAdmin):
    """Admin para auditar conversaciones del bot"""
    list_display = ('participant_display', 'created_at', 'was_blocked', 'block_reason', 'latency_ms', 'tokens_used')
    list_filter = ('was_blocked', 'block_reason', 'created_at')
    search_fields = ('user__phone_number', 'anonymous_user__session_id', 'anonymous_user__name', 'message', 'response')
    readonly_fields = ('user', 'anonymous_user', 'message', 'response', 'response_meta',
                      'was_blocked', 'block_reason', 'latency_ms', 'tokens_used', 'created_at')
    date_hierarchy = 'created_at'

    def participant_display(self, obj):
        """Muestra el participante de la conversación"""
        return obj.participant_identifier
    participant_display.short_description = 'Participante'

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
