# Crea el archivo zenzspa_project/profiles/admin.py con este contenido

from django.contrib import admin
from .models import UserProfile, LocalizedPain


class LocalizedPainInline(admin.TabularInline):
    model = LocalizedPain
    extra = 1


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'dosha', 'element', 'diet_type',
                    'sleep_quality', 'activity_level')
    search_fields = ('user__first_name', 'user__phone_number')
    list_filter = ('dosha', 'element', 'diet_type', 'sleep_quality')
    raw_id_fields = ('user',)
    inlines = [LocalizedPainInline]


@admin.register(LocalizedPain)
class LocalizedPainAdmin(admin.ModelAdmin):
    list_display = ('profile', 'body_part', 'pain_level', 'periodicity')
    search_fields = ('profile__user__first_name', 'body_part')
    list_filter = ('pain_level', 'periodicity')
    raw_id_fields = ('profile',)
