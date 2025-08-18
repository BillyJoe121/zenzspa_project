from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Punto de enganche para señales futuras (invalidaciones de caché, etc.).
        # No importamos nada aquí para evitar import cycles si aún no existen.
        return
