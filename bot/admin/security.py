from datetime import timedelta

from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from ..models import IPBlocklist, SuspiciousActivity


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
