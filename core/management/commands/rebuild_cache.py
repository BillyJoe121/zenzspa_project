from django.core.management.base import BaseCommand
from django.core.cache import cache

class Command(BaseCommand):
    help = "Reconstruye cachés comunes sin tumbar el servidor."

    def handle(self, *args, **options):
        # Enlaza con servicios reales cuando existan (catalogo, etc.)
        # Por ahora, limpia llaves conocidas.
        for key in ["catalog:services:v1", "catalog:categories:v1", "catalog:packages:v1", "global_settings"]:
            cache.delete(key)
            self.stdout.write(self.style.SUCCESS(f"Limpia: {key}"))
        self.stdout.write(self.style.SUCCESS("Listo."))
