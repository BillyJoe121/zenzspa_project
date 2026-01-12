"""
Admin interface para el módulo notifications.
Incluye métricas, estadísticas y herramientas de diagnóstico.
"""
from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin
import json

from .models import NotificationPreference, NotificationTemplate, NotificationLog


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "whatsapp_enabled",
        "email_enabled",
        "quiet_hours_range",
        "timezone"
    )
    list_filter = ("whatsapp_enabled", "email_enabled", "timezone")
    search_fields = ("user__email", "user__phone_number", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Usuario", {
            "fields": ("user",)
        }),
        ("Canales Habilitados", {
            "fields": ("whatsapp_enabled", "email_enabled", "sms_enabled", "push_enabled"),
            "description": "SMS y PUSH están deshabilitados. Use WhatsApp como alternativa."
        }),
        ("Horarios de Silencio", {
            "fields": ("quiet_hours_start", "quiet_hours_end", "timezone"),
            "description": "Define horarios en los que no se enviarán notificaciones (excepto críticas)"
        }),
        ("Metadatos", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def quiet_hours_range(self, obj):
        if obj.quiet_hours_start and obj.quiet_hours_end:
            return f"{obj.quiet_hours_start.strftime('%H:%M')} - {obj.quiet_hours_end.strftime('%H:%M')}"
        return "-"
    quiet_hours_range.short_description = "Horas de silencio"


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(SimpleHistoryAdmin):
    list_display = (
        "event_code",
        "channel",
        "is_active_colored",
        "validation_status",
        "preview_link",
        "usage_count",
        "created_at"
    )
    list_filter = ("channel", "is_active", "created_at")
    search_fields = ("event_code", "subject_template", "body_template")
    readonly_fields = ("created_at", "updated_at", "preview_display", "usage_stats")

    fieldsets = (
        ("Configuración", {
            "fields": ("event_code", "channel", "is_active")
        }),
        ("Plantilla", {
            "fields": ("subject_template", "body_template"),
            "description": "Use sintaxis Django Template: {{ variable }}"
        }),
        ("Preview", {
            "fields": ("preview_display",),
            "classes": ("collapse",)
        }),
        ("Estadísticas", {
            "fields": ("usage_stats",),
            "classes": ("collapse",)
        }),
        ("Metadatos", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def is_active_colored(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Activa</span>'
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">✗ Inactiva</span>'
        )
    is_active_colored.short_description = "Estado"

    def preview_link(self, obj):
        max_length = 50
        preview = obj.body_template[:max_length]
        if len(obj.body_template) > max_length:
            preview += "..."

        return format_html(
            '<span title="{}" style="font-family: monospace; font-size: 11px;">{}</span>',
            obj.body_template.replace('"', '&quot;'),
            preview
        )
    preview_link.short_description = "Preview"

    def preview_display(self, obj):
        """Muestra preview completo del template"""
        html = f"""
        <div style="padding: 10px; background: #f5f5f5; border-radius: 5px;">
            <h4>Subject Template:</h4>
            <pre style="background: white; padding: 10px; border: 1px solid #ddd;">{obj.subject_template or '(sin subject)'}</pre>

            <h4>Body Template:</h4>
            <pre style="background: white; padding: 10px; border: 1px solid #ddd;">{obj.body_template}</pre>
        </div>
        """
        return format_html(html)
    preview_display.short_description = "Vista Previa Completa"

    def usage_count(self, obj):
        """Muestra cuántas veces se ha usado este template"""
        count = NotificationLog.objects.filter(
            event_code=obj.event_code,
            channel=obj.channel
        ).count()
        return f"{count} envíos"
    usage_count.short_description = "Uso"

    def validation_status(self, obj):
        try:
            obj.full_clean()
            return format_html('<span style="color: green;">✓ Válida</span>')
        except Exception as exc:
            return format_html('<span style="color: red;" title="{}">✗ Inválida</span>', exc)
    validation_status.short_description = "Validación"

    def usage_stats(self, obj):
        """Estadísticas de uso del template"""
        logs = NotificationLog.objects.filter(
            event_code=obj.event_code,
            channel=obj.channel
        )

        stats = logs.aggregate(
            total=Count('id'),
            sent=Count('id', filter=Q(status=NotificationLog.Status.SENT)),
            failed=Count('id', filter=Q(status=NotificationLog.Status.FAILED)),
            queued=Count('id', filter=Q(status=NotificationLog.Status.QUEUED)),
        )

        html = f"""
        <div style="padding: 10px; background: #f5f5f5; border-radius: 5px;">
            <h4>Estadísticas de Uso:</h4>
            <table style="width: 100%;">
                <tr><td><strong>Total envíos:</strong></td><td>{stats['total']}</td></tr>
                <tr><td><strong>Exitosos:</strong></td><td style="color: green;">{stats['sent']}</td></tr>
                <tr><td><strong>Fallidos:</strong></td><td style="color: red;">{stats['failed']}</td></tr>
                <tr><td><strong>En cola:</strong></td><td style="color: orange;">{stats['queued']}</td></tr>
                <tr><td><strong>Tasa de éxito:</strong></td><td>{(stats['sent'] / stats['total'] * 100) if stats['total'] > 0 else 0:.1f}%</td></tr>
            </table>
        </div>
        """
        return format_html(html)
    usage_stats.short_description = "Estadísticas"


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "event_code",
        "user_display",
        "channel",
        "status_colored",
        "priority",
        "sent_at",
        "attempts_display",
        "created_at"
    )
    list_filter = (
        "channel",
        "status",
        "priority",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = ("event_code", "user__email", "user__phone_number")
    raw_id_fields = ("user",)
    readonly_fields = (
        "status_colored",
        "attempts_display",
        "metadata_display",
        "payload_display",
        "created_at",
        "updated_at"
    )
    date_hierarchy = "created_at"

    fieldsets = (
        ("Información Básica", {
            "fields": ("user", "event_code", "channel", "priority")
        }),
        ("Estado", {
            "fields": ("status_colored", "error_message", "sent_at")
        }),
        ("Contenido", {
            "fields": ("payload_display",),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("metadata_display", "attempts_display"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def user_display(self, obj):
        if not obj.user:
            return "-"
        return format_html(
            '<a href="/admin/users/customuser/{}/change/">{}</a>',
            obj.user.id,
            obj.user.email or obj.user.phone_number
        )
    user_display.short_description = "Usuario"

    def status_colored(self, obj):
        colors = {
            NotificationLog.Status.SENT: "green",
            NotificationLog.Status.FAILED: "red",
            NotificationLog.Status.QUEUED: "orange",
            NotificationLog.Status.SILENCED: "gray",
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = "Estado"

    def attempts_display(self, obj):
        metadata = obj.metadata or {}
        attempts = metadata.get("attempts", 0)
        max_attempts = metadata.get("max_attempts", 3)

        if obj.status == NotificationLog.Status.FAILED:
            color = "red" if attempts >= max_attempts else "orange"
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}/{}</span>',
                color, attempts, max_attempts
            )
        return f"{attempts}/{max_attempts}"
    attempts_display.short_description = "Intentos"

    def metadata_display(self, obj):
        return format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; max-height: 400px; overflow: auto;">{}</pre>',
            json.dumps(obj.metadata, indent=2, ensure_ascii=False)
        )
    metadata_display.short_description = "Metadata (JSON)"

    def payload_display(self, obj):
        return format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 5px; max-height: 400px; overflow: auto;">{}</pre>',
            json.dumps(obj.payload, indent=2, ensure_ascii=False)
        )
    payload_display.short_description = "Payload (JSON)"

    def changelist_view(self, request, extra_context=None):
        """Agregar estadísticas al listado"""
        extra_context = extra_context or {}

        # Stats de hoy
        today = timezone.now().date()
        today_logs = NotificationLog.objects.filter(created_at__date=today)

        stats = today_logs.aggregate(
            total=Count('id'),
            sent=Count('id', filter=Q(status=NotificationLog.Status.SENT)),
            failed=Count('id', filter=Q(status=NotificationLog.Status.FAILED)),
            queued=Count('id', filter=Q(status=NotificationLog.Status.QUEUED)),
            silenced=Count('id', filter=Q(status=NotificationLog.Status.SILENCED)),
        )

        # Stats por canal (hoy)
        channel_stats = today_logs.values('channel').annotate(
            count=Count('id'),
            sent=Count('id', filter=Q(status=NotificationLog.Status.SENT)),
            failed=Count('id', filter=Q(status=NotificationLog.Status.FAILED)),
        ).order_by('-count')

        extra_context['today_stats'] = {
            'total': stats['total'] or 0,
            'sent': stats['sent'] or 0,
            'failed': stats['failed'] or 0,
            'queued': stats['queued'] or 0,
            'silenced': stats['silenced'] or 0,
            'success_rate': (
                round(stats['sent'] / stats['total'] * 100, 1)
                if stats['total'] > 0 else 0
            ),
        }
        extra_context['channel_stats'] = list(channel_stats)

        return super().changelist_view(request, extra_context)
