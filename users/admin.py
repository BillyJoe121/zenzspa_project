from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import BlockedDevice, BlockedPhoneNumber, CustomUser


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('phone_number', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_verified', 'created_at')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'is_persona_non_grata')
    search_fields = ('phone_number', 'email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    
    # --- INICIO DE LA MODIFICACIÓN ---
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permisos y Rol', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'role', 'groups', 'user_permissions')}),
        ('Estado "Persona Non Grata"', {'fields': ('is_persona_non_grata', 'internal_notes', 'internal_photo_url')}),
        ('Fechas Importantes', {'fields': ('last_login', 'created_at')}),
    )
    # --- FIN DE LA MODIFICACIÓN ---
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'email', 'first_name', 'last_name', 'password'),
        }),
    )
    
    readonly_fields = ('last_login', 'created_at')

admin.site.register(CustomUser, CustomUserAdmin)


@admin.register(BlockedPhoneNumber)
class BlockedPhoneNumberAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "notes", "created_at")
    search_fields = ("phone_number",)


@admin.register(BlockedDevice)
class BlockedDeviceAdmin(admin.ModelAdmin):
    """
    Panel de administración para dispositivos bloqueados.

    Permite a los administradores ver, bloquear y desbloquear dispositivos
    basándose en su fingerprint (hash del User-Agent).
    """
    list_display = ("device_fingerprint_short", "user", "is_blocked", "reason", "ip_address", "created_at")
    list_filter = ("is_blocked", "created_at")
    search_fields = ("device_fingerprint", "user__phone_number", "user__email", "ip_address", "reason")
    readonly_fields = ("device_fingerprint", "user_agent", "created_at", "updated_at")

    fieldsets = (
        ("Información del Dispositivo", {
            "fields": ("device_fingerprint", "user_agent", "ip_address"),
        }),
        ("Estado del Bloqueo", {
            "fields": ("is_blocked", "reason"),
        }),
        ("Asociación con Usuario", {
            "fields": ("user",),
        }),
        ("Metadatos", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def device_fingerprint_short(self, obj):
        """Muestra una versión corta del fingerprint para legibilidad."""
        return f"{obj.device_fingerprint[:16]}..."
    device_fingerprint_short.short_description = "Fingerprint"
