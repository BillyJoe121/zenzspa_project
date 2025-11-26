from django.contrib import admin
from django.db import models
from django.utils import timezone
from django.utils.html import format_html
from .models import (
    BotConfiguration, BotConversationLog, AnonymousUser,
    HumanHandoffRequest, HumanMessage, SuspiciousActivity, IPBlocklist
)


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



class HumanMessageInline(admin.TabularInline):
    """Inline para mostrar mensajes dentro del handoff request"""
    model = HumanMessage
    extra = 0
    readonly_fields = ('sender', 'sender_name', 'is_from_staff', 'from_anonymous',
                      'message', 'created_at', 'read_at')
    fields = ('sender_name', 'is_from_staff', 'message', 'created_at', 'read_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # No permitir agregar mensajes desde el inline
        return False


@admin.register(HumanHandoffRequest)
class HumanHandoffRequestAdmin(admin.ModelAdmin):
    """Admin para solicitudes de escalamiento a atención humana"""
    list_display = ('client_identifier', 'client_score', 'escalation_reason',
                   'status', 'assigned_to', 'created_at', 'response_time_display')
    list_filter = ('status', 'escalation_reason', 'created_at', 'assigned_to')
    search_fields = ('user__phone_number', 'user__first_name', 'user__last_name',
                    'anonymous_user__name', 'anonymous_user__email', 'internal_notes')
    readonly_fields = ('user', 'anonymous_user', 'conversation_log', 'client_score',
                      'escalation_reason', 'created_at', 'client_contact_display',
                      'conversation_context_display', 'client_interests_display',
                      'response_time_display', 'resolution_time_display')
    date_hierarchy = 'created_at'
    inlines = [HumanMessageInline]

    fieldsets = (
        ('Cliente', {
            'fields': ('user', 'anonymous_user', 'client_contact_display', 'client_score')
        }),
        ('Escalamiento', {
            'fields': ('escalation_reason', 'conversation_log', 'created_at')
        }),
        ('Estado', {
            'fields': ('status', 'assigned_to', 'assigned_at', 'resolved_at',
                      'response_time_display', 'resolution_time_display')
        }),
        ('Contexto', {
            'fields': ('conversation_context_display', 'client_interests_display'),
            'classes': ('collapse',)
        }),
        ('Notas Internas', {
            'fields': ('internal_notes',)
        }),
    )

    def client_contact_display(self, obj):
        """Muestra información de contacto del cliente"""
        info = obj.client_contact_info
        return f"{info.get('name', 'N/A')}\nEmail: {info.get('email', 'N/A')}\nTel: {info.get('phone', 'N/A')}"
    client_contact_display.short_description = 'Información de Contacto'

    def conversation_context_display(self, obj):
        """Muestra el contexto de conversación formateado"""
        import json
        return json.dumps(obj.conversation_context, indent=2, ensure_ascii=False)
    conversation_context_display.short_description = 'Contexto de Conversación'

    def client_interests_display(self, obj):
        """Muestra los intereses del cliente formateados"""
        import json
        return json.dumps(obj.client_interests, indent=2, ensure_ascii=False)
    client_interests_display.short_description = 'Intereses del Cliente'

    def response_time_display(self, obj):
        """Muestra el tiempo de respuesta"""
        rt = obj.response_time
        return f"{rt} minutos" if rt is not None else "Sin asignar"
    response_time_display.short_description = 'Tiempo de Respuesta'

    def resolution_time_display(self, obj):
        """Muestra el tiempo de resolución"""
        rt = obj.resolution_time
        return f"{rt} minutos" if rt is not None else "Sin resolver"
    resolution_time_display.short_description = 'Tiempo de Resolución'

    # Acciones personalizadas
    actions = ['assign_to_me', 'mark_as_resolved']

    def assign_to_me(self, request, queryset):
        """Acción para asignarse las solicitudes seleccionadas"""
        count = 0
        for handoff in queryset.filter(status=HumanHandoffRequest.Status.PENDING):
            handoff.assigned_to = request.user
            handoff.status = HumanHandoffRequest.Status.ASSIGNED
            handoff.assigned_at = timezone.now()
            handoff.save()
            count += 1

        self.message_user(request, f"{count} solicitud(es) asignada(s) a ti.")
    assign_to_me.short_description = "Asignarme las solicitudes seleccionadas"

    def mark_as_resolved(self, request, queryset):
        """Acción para marcar solicitudes como resueltas"""
        count = queryset.filter(status__in=[
            HumanHandoffRequest.Status.ASSIGNED,
            HumanHandoffRequest.Status.IN_PROGRESS
        ]).update(
            status=HumanHandoffRequest.Status.RESOLVED,
            resolved_at=timezone.now()
        )

        self.message_user(request, f"{count} solicitud(es) marcada(s) como resuelta(s).")
    mark_as_resolved.short_description = "Marcar como resueltas"

    def has_add_permission(self, request):
        # No permitir crear handoffs manualmente
        return False

    def has_change_permission(self, request, obj=None):
        # STAFF y ADMIN pueden cambiar (asignar, resolver, agregar notas)
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )

    def has_delete_permission(self, request, obj=None):
        # Solo ADMIN puede eliminar handoffs
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_view_permission(self, request, obj=None):
        """ADMIN y STAFF pueden ver handoffs"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )


@admin.register(HumanMessage)
class HumanMessageAdmin(admin.ModelAdmin):
    """Admin para mensajes de conversación humana"""
    list_display = ('handoff_request', 'sender_name', 'direction_display',
                   'message_preview', 'created_at', 'is_unread')
    list_filter = ('is_from_staff', 'created_at', 'read_at')
    search_fields = ('message', 'handoff_request__user__phone_number',
                    'handoff_request__anonymous_user__name')
    readonly_fields = ('handoff_request', 'sender', 'sender_name', 'is_from_staff',
                      'from_anonymous', 'message', 'created_at', 'read_at')
    date_hierarchy = 'created_at'

    def direction_display(self, obj):
        """Muestra la dirección del mensaje"""
        return "→ Cliente" if obj.is_from_staff else "← Cliente"
    direction_display.short_description = 'Dirección'

    def message_preview(self, obj):
        """Muestra un preview del mensaje"""
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Mensaje'

    def has_add_permission(self, request):
        # No permitir crear mensajes manualmente desde admin
        return False

    def has_change_permission(self, request, obj=None):
        # No permitir editar mensajes
        return False

    def has_delete_permission(self, request, obj=None):
        # Solo ADMIN puede eliminar mensajes
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_view_permission(self, request, obj=None):
        """ADMIN y STAFF pueden ver mensajes"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )


@admin.register(IPBlocklist)
class IPBlocklistAdmin(admin.ModelAdmin):
    """Admin para gestionar IPs bloqueadas"""
    list_display = ('ip_address', 'reason_display', 'blocked_by_display', 'is_effective_display', 'created_at', 'expires_at_display')
    list_filter = ('is_active', 'reason', 'created_at')
    search_fields = ('ip_address', 'notes')
    readonly_fields = ('blocked_by', 'created_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Información del Bloqueo', {
            'fields': ('ip_address', 'reason', 'is_active')
        }),
        ('Detalles', {
            'fields': ('notes', 'expires_at')
        }),
        ('Auditoría', {
            'fields': ('blocked_by', 'created_at')
        }),
    )

    def reason_display(self, obj):
        """Muestra la razón del bloqueo con color"""
        colors = {
            'ABUSE': 'red',
            'MALICIOUS_CONTENT': 'darkred',
            'SPAM': 'orange',
            'FRAUD': 'purple',
            'MANUAL': 'gray',
        }
        color = colors.get(obj.reason, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_reason_display()
        )
    reason_display.short_description = 'Razón'

    def blocked_by_display(self, obj):
        """Muestra quién bloqueó la IP"""
        if obj.blocked_by:
            return obj.blocked_by.get_full_name() or obj.blocked_by.phone_number
        return "Sistema"
    blocked_by_display.short_description = 'Bloqueado Por'

    def is_effective_display(self, obj):
        """Muestra si el bloqueo está activo"""
        if obj.is_effective:
            return format_html('<span style="color: green; font-weight: bold;">✓ Activo</span>')
        return format_html('<span style="color: red;">✗ Inactivo</span>')
    is_effective_display.short_description = 'Estado'

    def expires_at_display(self, obj):
        """Muestra la fecha de expiración"""
        if obj.expires_at is None:
            return format_html('<span style="color: orange; font-weight: bold;">Permanente</span>')
        return obj.expires_at.strftime('%Y-%m-%d %H:%M')
    expires_at_display.short_description = 'Expira'

    # Acciones personalizadas
    actions = ['activate_blocks', 'deactivate_blocks']

    def activate_blocks(self, request, queryset):
        """Activar bloqueos seleccionados"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} bloqueo(s) activado(s).")
    activate_blocks.short_description = "Activar bloqueos seleccionados"

    def deactivate_blocks(self, request, queryset):
        """Desactivar bloqueos seleccionados"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} bloqueo(s) desactivado(s).")
    deactivate_blocks.short_description = "Desactivar bloqueos seleccionados"

    def save_model(self, request, obj, form, change):
        """Agregar el usuario que crea el bloqueo"""
        if not change:  # Si es nuevo
            obj.blocked_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        """Solo ADMIN puede agregar bloqueos"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_change_permission(self, request, obj=None):
        """Solo ADMIN puede editar bloqueos"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_delete_permission(self, request, obj=None):
        """Solo ADMIN puede eliminar bloqueos"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_view_permission(self, request, obj=None):
        """ADMIN y STAFF pueden ver bloqueos"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    """Admin para revisar actividades sospechosas"""
    list_display = ('participant_display', 'ip_address', 'activity_type_display', 'severity_display',
                   'created_at', 'reviewed_display', 'reviewed_by_display')
    list_filter = ('activity_type', 'severity', 'reviewed', 'created_at')
    search_fields = ('ip_address', 'description', 'user__phone_number', 'anonymous_user__name')
    readonly_fields = ('user', 'anonymous_user', 'ip_address', 'activity_type', 'severity',
                      'description', 'context_display', 'conversation_log', 'created_at',
                      'reviewed_by', 'reviewed_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Usuario', {
            'fields': ('user', 'anonymous_user', 'participant_display')
        }),
        ('Actividad Sospechosa', {
            'fields': ('activity_type', 'severity', 'ip_address', 'created_at')
        }),
        ('Detalles', {
            'fields': ('description', 'context_display', 'conversation_log')
        }),
        ('Revisión', {
            'fields': ('reviewed', 'reviewed_by', 'reviewed_at', 'admin_notes')
        }),
    )

    def participant_display(self, obj):
        """Muestra el participante"""
        return obj.participant_identifier
    participant_display.short_description = 'Usuario/IP'

    def activity_type_display(self, obj):
        """Muestra el tipo de actividad con color"""
        colors = {
            'JAILBREAK_ATTEMPT': 'darkred',
            'MALICIOUS_CONTENT': 'darkred',
            'REPETITIVE_MESSAGES': 'orange',
            'RATE_LIMIT_HIT': 'orange',
            'DAILY_LIMIT_HIT': 'red',
            'OFF_TOPIC_SPAM': 'orange',
            'EXCESSIVE_TOKENS': 'blue',
            'IP_ROTATION': 'purple',
        }
        color = colors.get(obj.activity_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_activity_type_display()
        )
    activity_type_display.short_description = 'Tipo'

    def severity_display(self, obj):
        """Muestra la severidad con color"""
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            obj.severity_color, obj.get_severity_display()
        )
    severity_display.short_description = 'Severidad'

    def reviewed_display(self, obj):
        """Muestra si fue revisado"""
        if obj.reviewed:
            return format_html('<span style="color: green; font-weight: bold;">✓ Revisado</span>')
        return format_html('<span style="color: red; font-weight: bold;">✗ Pendiente</span>')
    reviewed_display.short_description = 'Estado'

    def reviewed_by_display(self, obj):
        """Muestra quién revisó"""
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.phone_number
        return "-"
    reviewed_by_display.short_description = 'Revisado Por'

    def context_display(self, obj):
        """Muestra el contexto formateado"""
        import json
        return format_html('<pre>{}</pre>', json.dumps(obj.context, indent=2, ensure_ascii=False))
    context_display.short_description = 'Contexto'

    # Acciones personalizadas
    actions = ['mark_as_reviewed', 'mark_as_unreviewed']

    def mark_as_reviewed(self, request, queryset):
        """Marcar como revisadas"""
        count = 0
        for activity in queryset.filter(reviewed=False):
            activity.mark_as_reviewed(request.user)
            count += 1
        self.message_user(request, f"{count} actividad(es) marcada(s) como revisada(s).")
    mark_as_reviewed.short_description = "Marcar como revisadas"

    def mark_as_unreviewed(self, request, queryset):
        """Marcar como no revisadas"""
        count = queryset.update(reviewed=False, reviewed_by=None, reviewed_at=None)
        self.message_user(request, f"{count} actividad(es) marcada(s) como no revisada(s).")
    mark_as_unreviewed.short_description = "Marcar como no revisadas"

    def changelist_view(self, request, extra_context=None):
        """Vista personalizada con estadísticas de actividades sospechosas"""
        from datetime import timedelta
        from django.db.models import Count

        extra_context = extra_context or {}

        # Estadísticas de los últimos 7 días
        week_ago = timezone.now() - timedelta(days=7)

        # Actividades por tipo
        activities_by_type = SuspiciousActivity.objects.filter(
            created_at__gte=week_ago
        ).values('activity_type').annotate(
            count=Count('id')
        ).order_by('-count')

        # Actividades por severidad
        activities_by_severity = SuspiciousActivity.objects.filter(
            created_at__gte=week_ago
        ).values('severity').annotate(
            count=Count('id')
        ).order_by('-severity')

        # Top 5 IPs con más actividades sospechosas
        top_ips = SuspiciousActivity.objects.filter(
            created_at__gte=week_ago
        ).values('ip_address').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Actividades pendientes de revisión
        pending_count = SuspiciousActivity.objects.filter(reviewed=False).count()

        extra_context['activities_by_type'] = activities_by_type
        extra_context['activities_by_severity'] = activities_by_severity
        extra_context['top_suspicious_ips'] = top_ips
        extra_context['pending_review_count'] = pending_count

        return super().changelist_view(request, extra_context=extra_context)

    def has_add_permission(self, request):
        """No permitir crear manualmente"""
        return False

    def has_change_permission(self, request, obj=None):
        """Solo ADMIN puede editar (para agregar notas y marcar como revisado)"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_delete_permission(self, request, obj=None):
        """Solo ADMIN puede eliminar"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role == CustomUser.Role.ADMIN
        )

    def has_view_permission(self, request, obj=None):
        """ADMIN y STAFF pueden ver"""
        from users.models import CustomUser
        return (
            request.user.is_superuser or
            request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        )
