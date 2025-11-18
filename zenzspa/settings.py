from pathlib import Path
import os
from datetime import timedelta
from typing import Dict

from dotenv import load_dotenv

# Carga de variables de entorno temprana
load_dotenv()

# --------------------------------------------------------------------------------------
# Paths básicos
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------------------
# Claves y modo
# --------------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no configurada. Define la variable de entorno antes de iniciar la aplicación.")
DEBUG = os.getenv("DEBUG", "0") in ("1", "true", "True")

# Hosts/CSRF/CORS: admite coma o espacio


def _split_env(name, default=""):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.replace(",", " ").split() if x.strip()]


def _parse_action_scores(raw: str) -> Dict[str, float]:
    """
    Convierte una cadena tipo 'otp:0.7,verify:0.3' en un dict.
    Ignora pares malformados para no frenar el arranque.
    """
    mapping: dict[str, float] = {}
    for chunk in raw.split(","):
        if ":" not in chunk:
            continue
        action, score = chunk.split(":", 1)
        try:
            mapping[action.strip()] = float(score.strip())
        except ValueError:
            continue
    return mapping


ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS", "localhost 127.0.0.1")
CSRF_TRUSTED_ORIGINS = _split_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost http://127.0.0.1 http://localhost:3000 http://127.0.0.1:3000",
)
CORS_ALLOWED_ORIGINS = _split_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000 http://127.0.0.1:3000",
)

# --------------------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",                  # CORS
    "csp",                   # Content Security Policy
    "simple_history",
    # "axes",                       # Descomenta si usas django-axes para login clásico

    # Tus apps
    "users",
    "spa",
    "profiles",
    "core",
    "marketplace",
    "notifications",
    "analytics",
    "bot",
    "finances",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS antes de CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "profiles.middleware.KioskFlowEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "core.middleware.RequestIDMiddleware",
    "core.middleware.AdminAuditMiddleware",
    # "axes.middleware.AxesMiddleware",               # Habilita si usas django-axes
]

ROOT_URLCONF = "zenzspa.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "zenzspa.wsgi.application"

# --------------------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "zenzspa"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "prefer")},
    }
}

# --------------------------------------------------------------------------------------
# Usuario
# --------------------------------------------------------------------------------------
AUTH_USER_MODEL = "users.CustomUser"

# --------------------------------------------------------------------------------------
# DRF
# --------------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": int(os.getenv("API_PAGE_SIZE", "20")),
    # Throttling básico de sentido común. Ajusta según tus endpoints críticos.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": os.getenv("THROTTLE_USER", "200/min"),
        "anon": os.getenv("THROTTLE_ANON", "60/min"),
        # Ejemplos de scopes específicos
        "auth_login": os.getenv("THROTTLE_AUTH_LOGIN", "5/min"),
        "auth_verify": os.getenv("THROTTLE_AUTH_VERIFY", "3/10min"),
        "payments": os.getenv("THROTTLE_PAYMENTS", "60/min"),
        "bot": os.getenv("THROTTLE_BOT", "10/min"),
    },
}

# --------------------------------------------------------------------------------------
# Simple JWT
# --------------------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MIN", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": os.getenv("JWT_ALG", "HS256"),
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    # Tu modelo usa phone_number como identificador
    "USER_ID_FIELD": "phone_number",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
}

# --------------------------------------------------------------------------------------
# Caché (Redis)
# --------------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "300")),
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# --------------------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": int(os.getenv("PASSWORD_MIN_LENGTH", "8"))}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------------------
# i18n
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static/Media
# --------------------------------------------------------------------------------------
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------------------------------------------
# Primary key
# --------------------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------------------
# Integraciones ( Twilio / Wompi )
# --------------------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")

RECAPTCHA_V3_SITE_KEY = os.getenv("RECAPTCHA_V3_SITE_KEY", "")
RECAPTCHA_V3_SECRET_KEY = os.getenv("RECAPTCHA_V3_SECRET_KEY") or os.getenv("RECAPTCHA_SECRET_KEY", "")
RECAPTCHA_V3_DEFAULT_SCORE = float(os.getenv("RECAPTCHA_V3_DEFAULT_SCORE", "0.5"))
RECAPTCHA_V3_ACTION_SCORES = _parse_action_scores(os.getenv("RECAPTCHA_V3_ACTION_SCORES", ""))

KIOSK_SESSION_TIMEOUT_MINUTES = int(os.getenv("KIOSK_SESSION_TIMEOUT_MINUTES", "10"))
KIOSK_SECURE_SCREEN_URL = os.getenv("KIOSK_SECURE_SCREEN_URL", "/kiosk/secure")
KIOSK_ALLOWED_PATH_PREFIXES = tuple(
    _split_env(
        "KIOSK_ALLOWED_PATH_PREFIXES",
        "/api/v1/kiosk/ /api/v1/users/ /api/v1/dosha-quiz/",
    )
)
KIOSK_ALLOWED_VIEW_NAMES = set(
    _split_env(
        "KIOSK_ALLOWED_VIEW_NAMES",
        "clinical-profile-me clinical-profile-list clinical-profile-detail clinical-profile-update",
    )
)

WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY", "")
WOMPI_INTEGRITY_SECRET = os.getenv("WOMPI_INTEGRITY_SECRET", "")
# Alias compatible con la documentación más reciente.
WOMPI_INTEGRITY_KEY = os.getenv("WOMPI_INTEGRITY_KEY", WOMPI_INTEGRITY_SECRET)
WOMPI_EVENT_SECRET = os.getenv("WOMPI_EVENT_SECRET", "")
WOMPI_REDIRECT_URL = os.getenv(
    "WOMPI_REDIRECT_URL", "http://localhost:3000/payment-result")

# --------------------------------------------------------------------------------------
# CORS/CSRF
# --------------------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

# --------------------------------------------------------------------------------------
# Seguridad adicional en prod
# --------------------------------------------------------------------------------------
SECURE_SSL_REDIRECT = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.getenv("HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --------------------------------------------------------------------------------------
# CSP (django-csp) V4.0+
# --------------------------------------------------------------------------------------
CSP_DIRECTIVES = {
    "default-src": ("'self'",),
    "script-src": ("'self'", "cdn.jsdelivr.net", "unpkg.com"),
    "style-src": ("'self'", "fonts.googleapis.com", "cdn.jsdelivr.net", "unpkg.com"),
    "img-src": ("'self'", "data:", "blob:"),
    "font-src": ("'self'", "fonts.gstatic.com", "cdn.jsdelivr.net", "unpkg.com"),
    "connect-src": tuple(["'self'"] + CORS_ALLOWED_ORIGINS),
}

# --------------------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "check-for-reminders-every-hour": {
        "task": "spa.tasks.check_and_queue_reminders",
        "schedule": crontab(minute="0", hour="*"),
    },
    "cancel-unpaid-appointments-every-10-minutes": {
        "task": "spa.tasks.cancel_unpaid_appointments",
        "schedule": crontab(minute="*/10"),
    },
    "release-expired-order-reservations": {
        "task": "marketplace.tasks.release_expired_order_reservations",
        "schedule": crontab(minute="*/10"),
    },
    "developer-payout-hourly": {
        "task": "finances.tasks.run_developer_payout",
        "schedule": crontab(minute=0, hour="*"),
    },
}

# --------------------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------------------
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = os.getenv(
        "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.sendgrid.net")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") in ("1", "true", "True")
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "ZenzSpa <no-reply@zenzspa.com>")

# --------------------------------------------------------------------------------------
# Logging: útil para producción y depuración
# --------------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {
            "level": os.getenv("DB_LOG_LEVEL", "WARNING" if not DEBUG else "INFO"),
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

# --------------------------------------------------------------------------------------
# Sentry (opcional)
# --------------------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment=os.getenv(
            "SENTRY_ENV", "production" if not DEBUG else "development"),
    )

# --------------------------------------------------------------------------------------
# DRF Browsable API solo en debug
# --------------------------------------------------------------------------------------
if DEBUG:
    REST_FRAMEWORK.setdefault(
        "DEFAULT_RENDERER_CLASSES",
        (
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ),
    )
else:
    REST_FRAMEWORK.setdefault(
        "DEFAULT_RENDERER_CLASSES",
        ("rest_framework.renderers.JSONRenderer",),
    )

# --------------------------------------------------------------------------------------
# Axes (ejemplo de límites si usas login clásico por /admin)
# --------------------------------------------------------------------------------------
AXES_ENABLED = os.getenv("AXES_ENABLED", "0") in ("1", "true", "True")
if AXES_ENABLED:
    AXES_FAILURE_LIMIT = int(
        os.getenv("AXES_FAILURE_LIMIT", "5"))          # 5/min login
    AXES_COOLOFF_TIME = int(
        os.getenv("AXES_COOLOFF_TIME_MIN", "10"))       # 10 minutos
    AXES_ONLY_USER_FAILURES = False
    AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True
