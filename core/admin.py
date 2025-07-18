from django.contrib import admin
from .models import AuditLog, GlobalSettings

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'admin_user', 'target_user')
    list_filter = ('action', 'admin_user', 'created_at')
    search_fields = ('admin_user__phone_number', 'target_user__phone_number', 'details')
    readonly_fields = ('id', 'created_at', 'updated_at', 'action', 'admin_user', 'target_user', 'target_appointment', 'details')

    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    """
    Panel de administración para las Configuraciones Globales.
    """
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se añaden los nuevos campos a la vista del admin.
    fieldsets = (
        ('Capacidad y Pagos', {
            'fields': ('low_supervision_capacity', 'advance_payment_percentage')
        }),
        ('Gestión de Horarios', {
            'fields': ('appointment_buffer_time',)
        }),
    )
    # --- FIN DE LA MODIFICACIÓN ---

    def has_add_permission(self, request):
        return not GlobalSettings.objects.exists()
    def has_delete_permission(self, request, obj=None):
        return False