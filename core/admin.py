from django.contrib import admin
from .models import AuditLog, GlobalSettings


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
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
        # Auditoría se genera por el sistema; nunca manual en el admin.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    """
    Panel de administración para las Configuraciones Globales.
    Permite editar de forma segura parámetros operativos.
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
        # Singleton: solo una fila permitida
        from .models import GlobalSettings as GS
        return not GS.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        """
        Validación completa antes de guardar (incluye checks del modelo).
        """
        obj.full_clean()
        super().save_model(request, obj, form, change)
