from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import NotificationPreference, NotificationTemplate, NotificationLog


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_enabled", "sms_enabled", "push_enabled")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(SimpleHistoryAdmin):
    list_display = ("event_code", "channel", "is_active", "updated_at")
    list_filter = ("channel", "is_active")
    search_fields = ("event_code", "subject_template")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_code", "user", "channel", "status", "sent_at")
    list_filter = ("channel", "status")
    search_fields = ("event_code", "user__email")
    raw_id_fields = ("user",)
