from django.contrib import admin
from django.utils import timezone

from ..models import HumanHandoffRequest, HumanMessage


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

