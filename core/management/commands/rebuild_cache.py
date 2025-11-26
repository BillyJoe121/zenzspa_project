from django.core.management.base import BaseCommand
from django.core.cache import cache
from core.caching import CacheKeys

class Command(BaseCommand):
    help = "Reconstruye cachés comunes sin tumbar el servidor."

    def handle(self, *args, **options):
        # Limpia todas las llaves de caché conocidas
        cache_keys = [
            CacheKeys.SERVICES,
            CacheKeys.CATEGORIES,
            CacheKeys.PACKAGES,
            CacheKeys.GLOBAL_SETTINGS,  # Ahora usa la llave correcta
        ]

        for key in cache_keys:
            cache.delete(key)
            self.stdout.write(self.style.SUCCESS(f"Limpia: {key}"))

        self.stdout.write(self.style.SUCCESS("✓ Caché reconstruido exitosamente."))
