from django.apps import AppConfig


class SpaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'spa'

    def ready(self):
        """Import signals when the app is ready."""
        import spa.signals  # noqa: F401
