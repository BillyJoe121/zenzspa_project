from django.contrib import admin
from .models import BotConfiguration


@admin.register(BotConfiguration)
class BotConfigurationAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'is_active', 'booking_url')

    # Truco para impedir que creen más de una configuración (Singleton)
    def has_add_permission(self, request):
        return not BotConfiguration.objects.exists()
