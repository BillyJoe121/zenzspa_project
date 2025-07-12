from django.contrib import admin
from .models import ClinicalProfile, LocalizedPain, DoshaQuestion, DoshaOption, ClientDoshaAnswer

class LocalizedPainInline(admin.TabularInline):
    model = LocalizedPain
    extra = 1
    raw_id_fields = ('profile',)

@admin.register(ClinicalProfile)
class ClinicalProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'dosha', 'element', 'updated_at')
    list_filter = ('dosha', 'element', 'sleep_quality', 'activity_level')
    search_fields = ('user__phone_number', 'user__first_name', 'user__last_name', 'user__email')
    raw_id_fields = ('user',)
    inlines = [LocalizedPainInline]
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Información del Usuario', {'fields': ('user', 'id')}),
        ('Perfil Holístico', {'fields': ('dosha', 'element', 'diet_type', 'sleep_quality', 'activity_level')}),
        ('Historial y Notas', {'fields': ('accidents_notes', 'general_notes')}),
        ('Auditoría', {'fields': ('created_at', 'updated_at')}),
    )

@admin.register(LocalizedPain)
class LocalizedPainAdmin(admin.ModelAdmin):
    list_display = ('profile', 'body_part', 'pain_level', 'periodicity')
    search_fields = ('profile__user__first_name', 'profile__user__last_name', 'body_part')
    list_filter = ('pain_level', 'periodicity', 'body_part')
    raw_id_fields = ('profile',)

# --- INICIO DE LA MODIFICACIÓN ---

class DoshaOptionInline(admin.TabularInline):
    """Permite editar las opciones directamente en la vista de la pregunta."""
    model = DoshaOption
    extra = 3 # Muestra 3 campos para las 3 opciones (Vata, Pitta, Kapha)

@admin.register(DoshaQuestion)
class DoshaQuestionAdmin(admin.ModelAdmin):
    """Configuración para el modelo de Preguntas de Dosha."""
    list_display = ('category', 'text')
    list_filter = ('category',)
    search_fields = ('text',)
    inlines = [DoshaOptionInline]

@admin.register(ClientDoshaAnswer)
class ClientDoshaAnswerAdmin(admin.ModelAdmin):
    """Configuración para ver las respuestas de los clientes."""
    list_display = ('profile', 'question', 'selected_option')
    search_fields = ('profile__user__first_name', 'question__text')
    raw_id_fields = ('profile', 'question', 'selected_option')

# --- FIN DE LA MODIFICACIÓN ---