from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    """
    Configuración personalizada para el modelo CustomUser en el panel de administración.
    """
    model = CustomUser
    # Se reemplaza 'date_joined' por 'created_at' que es el campo heredado.
    list_display = ('phone_number', 'email', 'first_name',
                    'last_name', 'role', 'is_staff', 'is_verified', 'created_at')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('phone_number', 'email', 'first_name', 'last_name')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Información Personal', {
         'fields': ('first_name', 'last_name', 'email')}),
        ('Permisos y Rol', {'fields': ('is_active', 'is_staff', 'is_superuser',
         'is_verified', 'role', 'groups', 'user_permissions')}),
        # 'created_at' estará en readonly_fields
        ('Fechas Importantes', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'email', 'first_name', 'last_name', 'password'),
        }),
    )

    # Se reemplaza 'date_joined' por 'created_at' que ahora es el campo de registro.
    readonly_fields = ('last_login', 'created_at')


admin.site.register(CustomUser, CustomUserAdmin)
