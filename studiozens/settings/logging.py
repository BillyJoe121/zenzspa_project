import os
import warnings
from pathlib import Path

from .base import BASE_DIR, DEBUG, INSTALLED_APPS, MIDDLEWARE, _split_env

# --------------------------------------------------------------------------------------
# Logging: útil para producción y depuración
# --------------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {process:d} {thread:d}: {message}",
            "style": "{",
        },
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "filters": {
        "sanitize_api_keys": {
            "()": "core.infra.logging_filters.SanitizeAPIKeyFilter",
        },
        "sanitize_pii": {
            "()": "core.infra.logging_filters.SanitizePIIFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
            "filters": ["sanitize_api_keys", "sanitize_pii"],
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "studiozens.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 10,
            "formatter": "verbose",
            "filters": ["sanitize_api_keys", "sanitize_pii"],
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "errors.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
            "filters": ["sanitize_api_keys", "sanitize_pii"],
        },
    },
    "root": {
        "handlers": ["console", "file", "error_file"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.db.backends": {
            "level": os.getenv("DB_LOG_LEVEL", "WARNING" if not DEBUG else "INFO"),
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "bot": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
}

# Crear directorio de logs si no existe
(BASE_DIR / "logs").mkdir(exist_ok=True)

# --------------------------------------------------------------------------------------
# Sentry (opcional)
# --------------------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    # STUDIOZENS-SENTRY-CELERY: Agregar integraciones completas
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment=os.getenv(
            "SENTRY_ENV", "production" if not DEBUG else "development"),
        release=os.getenv("GIT_COMMIT", "local"),
    )

# --------------------------------------------------------------------------------------
# APM (New Relic / Debug Toolbar)
# --------------------------------------------------------------------------------------
# STUDIOZENS-NEWRELIC-CONFIG: Configuración mejorada de New Relic
NEW_RELIC_LICENSE_KEY = os.getenv("NEW_RELIC_LICENSE_KEY", "")
NEW_RELIC_CONFIG_FILE = os.getenv("NEW_RELIC_CONFIG_FILE", str(BASE_DIR / "newrelic.ini"))
if NEW_RELIC_LICENSE_KEY and not DEBUG:
    try:
        import newrelic.agent

        config_path = Path(NEW_RELIC_CONFIG_FILE)
        if config_path.exists():
            newrelic.agent.initialize(
                config_file=config_path,
                environment=os.getenv("NEW_RELIC_ENV", "production"),
            )
        else:
            warnings.warn(
                f"New Relic config file not found: {NEW_RELIC_CONFIG_FILE}. "
                "APM monitoring will not be enabled.",
                RuntimeWarning
            )
    except ImportError:
        pass

if DEBUG:
    try:
        import debug_toolbar

        INSTALLED_APPS += ["debug_toolbar"]
        MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
        # STUDIOZENS-DEBUG-TOOLBAR: Soporte para IPv6 y Docker
        INTERNAL_IPS = _split_env("DEBUG_TOOLBAR_IPS", "127.0.0.1 ::1")

        DEBUG_TOOLBAR_CONFIG = {
            "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
            "SQL_WARNING_THRESHOLD": 100,  # 100ms
        }
    except ImportError:
        pass
