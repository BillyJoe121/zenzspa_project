from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Configuración del panel de administración para el modelo AuditLog.
    """
    # Se reemplaza 'timestamp' por 'created_at' en list_display.
    list_display = ('created_at', 'action', 'admin_user', 'target_user')

    # Se reemplaza 'timestamp' por 'created_at' en list_filter.
    list_filter = ('action', 'admin_user', 'created_at')

    search_fields = ('admin_user__phone_number',
                     'target_user__phone_number', 'details')

    # Campos de solo lectura, ya que los logs no deben ser modificables.
    readonly_fields = ('id', 'created_at', 'updated_at', 'action',
                       'admin_user', 'target_user', 'target_appointment', 'details')

    def has_add_permission(self, request):
        # Nadie debería poder añadir registros de auditoría manualmente.
        return False

    def has_delete_permission(self, request, obj=None):
        # Los registros de auditoría no deben ser eliminables.
        return False
