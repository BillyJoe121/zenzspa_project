"""
Configuración del panel de administración de Django para el módulo core.

Define las interfaces administrativas para los modelos principales del sistema:
- AuditLog: Registro de auditoría (solo lectura)
- GlobalSettings: Configuración global del sistema (singleton)
"""
from django.contrib import admin
from .models import AuditLog, GlobalSettings


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Panel de administración para el registro de auditoría.

    Características:
    - Solo lectura: No permite crear ni eliminar registros
    - Búsqueda por usuarios y detalles
    - Filtrado por acción y fecha
    - Jerarquía cronológica para navegación temporal
    """
    list_display = ("created_at", "action", "admin_user", "target_user", "target_appointment")
    list_filter = ("action", "admin_user", "created_at")
    search_fields = (
        "admin_user__phone_number",
        "target_user__phone_number",
        "details",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "action",
        "admin_user",
        "target_user",
        "target_appointment",
        "details",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        """
        Deshabilita la creación manual de registros de auditoría.

        Los registros de auditoría son generados automáticamente por el sistema
        y no deben ser creados manualmente por los administradores.
        """
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Deshabilita la eliminación de registros de auditoría.

        Los registros de auditoría deben ser inmutables para mantener
        la integridad del historial de acciones.
        """
        return False


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    """
    Panel de administración para las Configuraciones Globales del sistema.

    Maneja el modelo Singleton GlobalSettings que controla parámetros operativos
    críticos como capacidades, políticas de pago, configuración VIP, etc.

    Características:
    - Singleton: Solo permite una instancia del modelo
    - No permite eliminación para prevenir pérdida de configuración
    - Agrupa campos por categoría lógica en fieldsets
    - Ejecuta validaciones completas antes de guardar cambios
    """

    fieldsets = (
        ("Capacidad y Pagos", {
            "fields": ("low_supervision_capacity", "advance_payment_percentage"),
            "description": "Capacidad simultánea y porcentaje de anticipo requerido.",
        }),
        ("Gestión de Horarios", {
            "fields": ("appointment_buffer_time",),
            "description": "Minutos de limpieza/preparación entre citas.",
        }),
    )

    list_display = ("low_supervision_capacity", "advance_payment_percentage", "appointment_buffer_time", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")

    def has_add_permission(self, request):
        """
        Permite crear la instancia solo si no existe ninguna (patrón Singleton).

        Returns:
            bool: True si no existe ninguna instancia, False en caso contrario.
        """
        from .models import GlobalSettings as GS
        return not GS.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """
        Previene la eliminación de la configuración global.

        El sistema requiere que siempre exista una instancia de configuración.
        """
        return False

    def save_model(self, request, obj, form, change):
        """
        Ejecuta validaciones completas antes de guardar cambios.

        Llama a full_clean() para garantizar que todas las validaciones
        de modelo (incluyendo clean()) se ejecuten antes de persistir.

        Args:
            request: Petición HTTP actual
            obj: Instancia de GlobalSettings a guardar
            form: Formulario de admin
            change: True si es actualización, False si es creación
        """
        obj.full_clean()
        super().save_model(request, obj, form, change)
