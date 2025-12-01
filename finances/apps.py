from django.apps import AppConfig


class FinancesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finances"
    verbose_name = "Finances"

    def ready(self):
        """
        Valida variables críticas de Wompi en entornos no DEBUG para evitar despliegues incorrectos.
        """
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        if getattr(settings, "DEBUG", False):
            return

        required_vars = [
            "WOMPI_PUBLIC_KEY",
            "WOMPI_PRIVATE_KEY",
            "WOMPI_INTEGRITY_KEY",
            "WOMPI_EVENT_SECRET",
            "WOMPI_BASE_URL",
            "WOMPI_REDIRECT_URL",
        ]
        missing = [var for var in required_vars if not getattr(settings, var, None)]
        if missing:
            raise ImproperlyConfigured(f"Faltan variables Wompi: {', '.join(missing)}")
