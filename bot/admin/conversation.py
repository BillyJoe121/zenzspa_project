from django.contrib import admin
from django.db import models
from django.utils import timezone

from ..models import AnonymousUser, BotConversationLog


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
    """Admin para auditar conversaciones del bot con análisis de fraude"""
    list_display = ('participant_display', 'ip_address', 'created_at', 'was_blocked', 'block_reason', 'latency_ms', 'tokens_used')
    list_filter = ('was_blocked', 'block_reason', 'created_at', 'ip_address')
    search_fields = ('user__phone_number', 'anonymous_user__session_id', 'anonymous_user__name', 'message', 'response', 'ip_address')
    readonly_fields = ('user', 'anonymous_user', 'message', 'response', 'response_meta',
                      'was_blocked', 'block_reason', 'latency_ms', 'tokens_used', 'ip_address', 'created_at')
    date_hierarchy = 'created_at'

    def participant_display(self, obj):
        """Muestra el participante de la conversación"""
        return obj.participant_identifier
    participant_display.short_description = 'Participante'

    def changelist_view(self, request, extra_context=None):
        """
        Vista personalizada con estadísticas de IPs sospechosas.
        Muestra las top 10 IPs por volumen de mensajes en los últimos 7 días.
        """
        from datetime import timedelta
        from django.db.models import Count, Sum
        
        extra_context = extra_context or {}
        
        # Top 10 IPs por volumen de mensajes (últimos 7 días)
        week_ago = timezone.now() - timedelta(days=7)
        
        top_ips = BotConversationLog.objects.filter(
            created_at__gte=week_ago,
            ip_address__isnull=False
        ).values('ip_address').annotate(
            message_count=Count('id'),
            total_tokens=Sum('tokens_used'),
            blocked_count=Count('id', filter=models.Q(was_blocked=True))
        ).order_by('-message_count')[:10]
        
        # Agregar flag de sospechoso (>40 mensajes/día en promedio)
        for ip in top_ips:
            avg_per_day = ip['message_count'] / 7
            ip['is_suspicious'] = avg_per_day > 40
            ip['avg_per_day'] = round(avg_per_day, 1)
        
        extra_context['top_ips'] = top_ips
        extra_context['analysis_period'] = '7 días'
        
        return super().changelist_view(request, extra_context=extra_context)

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

