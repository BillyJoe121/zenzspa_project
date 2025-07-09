from django.contrib import admin
from .models import ClinicalProfile, LocalizedPain

class LocalizedPainInline(admin.TabularInline):
    """Permite editar los dolores localizados directamente en el perfil clínico."""
    model = LocalizedPain
    extra = 1  # Muestra un campo vacío para añadir un nuevo dolor.
    raw_id_fields = ('profile',) # Mejora de rendimiento para ForeignKeys

@admin.register(ClinicalProfile)
class ClinicalProfileAdmin(admin.ModelAdmin):
    """Configuración del panel de administración para el Perfil Clínico."""
    list_display = ('user', 'dosha', 'element', 'updated_at')
    list_filter = ('dosha', 'element', 'sleep_quality', 'activity_level')
    search_fields = ('user__phone_number', 'user__first_name', 'user__last_name', 'user__email')
    raw_id_fields = ('user',) # Mejora de rendimiento para ForeignKeys
    inlines = [LocalizedPainInline]
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Información del Usuario', {
            'fields': ('user', 'id')
        }),
        ('Perfil Holístico', {
            'fields': ('dosha', 'element', 'diet_type', 'sleep_quality', 'activity_level')
        }),
        ('Historial y Notas', {
            'fields': ('accidents_notes', 'general_notes')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at')
        }),
    )

@admin.register(LocalizedPain)
class LocalizedPainAdmin(admin.ModelAdmin):
    """Configuración del panel de administración para los Dolores Localizados."""
    list_display = ('profile', 'body_part', 'pain_level', 'periodicity')
    search_fields = ('profile__user__first_name', 'profile__user__last_name', 'body_part')
    list_filter = ('pain_level', 'periodicity', 'body_part')
    raw_id_fields = ('profile',)
# --- FIN DE LA MODIFICACIÓN ---