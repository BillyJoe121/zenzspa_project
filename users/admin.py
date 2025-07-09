from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


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