from pathlib import Path
import os
from datetime import timedelta
from typing import Dict

from dotenv import load_dotenv

# Carga de variables de entorno temprana
load_dotenv()

def validate_required_env_vars():
    """
    Valida que todas las variables de entorno críticas estén configuradas.
    """
    required_vars = {
        "SECRET_KEY": "Clave secreta de Django",
        "DB_PASSWORD": "Contraseña de base de datos",
    }
    
    # En producción, validar más variables
    if os.getenv("DEBUG", "0") not in ("1", "true", "True"):
        required_vars.update({
            "TWILIO_ACCOUNT_SID": "Twilio Account SID",
            "TWILIO_AUTH_TOKEN": "Twilio Auth Token",
            "TWILIO_VERIFY_SERVICE_SID": "Twilio Verify Service SID",
            "WOMPI_PUBLIC_KEY": "Wompi Public Key",
            "WOMPI_INTEGRITY_SECRET": "Wompi Integrity Secret",
            "WOMPI_EVENT_SECRET": "Wompi Event Secret",
            "GEMINI_API_KEY": "Gemini API Key para bot",
            "REDIS_URL": "URL de Redis",
            "CELERY_BROKER_URL": "URL del broker de Celery",
            "EMAIL_HOST_USER": "Usuario de email",
            "EMAIL_HOST_PASSWORD": "Contraseña de email",
        })
    
    missing = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({description})")
    
    if missing:
        raise RuntimeError(
            f"Variables de entorno faltantes:\n" +
            "\n".join(f"  - {var}" for var in missing) +
            "\n\nConfigura estas variables en el archivo .env o como variables de entorno del sistema."
        )

# Validar variables al inicio
validate_required_env_vars()

# --------------------------------------------------------------------------------------
# Paths básicos
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------------------
# Claves y modo
# --------------------------------------------------------------------------------------
# Admite rotación de llaves secretas (Django 5.2+)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no configurada. Define la variable de entorno antes de iniciar la aplicación.")

# Configuración de encriptación Fernet para datos sensibles (HIPAA/GDPR Compliance)
FERNET_KEYS = [
    os.getenv('FERNET_KEY', '').encode() if os.getenv('FERNET_KEY') else None
]
if not FERNET_KEYS[0]:
    if os.getenv("DEBUG", "0") in ("1", "true", "True"):
        from cryptography.fernet import Fernet
        FERNET_KEYS = [Fernet.generate_key()]
        import warnings
        warnings.warn("FERNET_KEY no configurada. Usando clave temporal.", RuntimeWarning)
    else:
        raise RuntimeError("FERNET_KEY no configurada.")
DEBUG = os.getenv("DEBUG", "0") in ("1", "true", "True")

# Helper para listas (definido antes de usarse)
def _split_env(name, default=""):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.replace(",", " ").split() if x.strip()]

# SECRET_KEY_FALLBACKS debe definirse después del helper
SECRET_KEY_FALLBACKS = _split_env("SECRET_KEY_FALLBACKS")

# Hosts/CSRF/CORS: admite coma o espacio


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

# Validar CORS/CSRF en producción
if not DEBUG:
    # ZENZSPA-SEC-ALLOWED-HOSTS: Validar dominios productivos
    raw_hosts = os.getenv("ALLOWED_HOSTS", "")
    if not raw_hosts:
        raise RuntimeError("ALLOWED_HOSTS debe definirse en producción.")
    for host in ALLOWED_HOSTS:
        if host in {"localhost", "127.0.0.1", "[::1]"}:
            raise RuntimeError(f"Host inválido en producción: {host}")
    
    if not os.getenv("CORS_ALLOWED_ORIGINS"):
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS debe estar configurado en producción. "
            "Define los orígenes permitidos en el archivo .env."
        )
    
    # Validar que no haya localhost en producción
    for origin in CORS_ALLOWED_ORIGINS:
        if "localhost" in origin or "127.0.0.1" in origin:
            raise RuntimeError(
                f"Origen localhost detectado en producción: {origin}. "
                "Configura CORS_ALLOWED_ORIGINS con dominios de producción."
            )

    if not os.getenv("CSRF_TRUSTED_ORIGINS"):
        raise RuntimeError(
            "CSRF_TRUSTED_ORIGINS debe estar configurado en producción."
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
    "core.middleware.PerformanceLoggingMiddleware",  # NUEVO - Logging de performance
    # "axes.middleware.AxesMiddleware",               # Habilita si usas django-axes
]

# --------------------------------------------------------------------------------------
# Performance Monitoring
# --------------------------------------------------------------------------------------
SLOW_REQUEST_THRESHOLD = float(os.getenv("SLOW_REQUEST_THRESHOLD", "1.0"))  # segundos

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
        "OPTIONS": {
            "sslmode": os.getenv("DB_SSLMODE", "require" if not DEBUG else "prefer"),
            "connect_timeout": 10,
        },
    }
}

if not DEBUG and not os.getenv("DB_PASSWORD"):
    raise RuntimeError("DB_PASSWORD debe estar configurado en producción.")

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
    # ZENZSPA-API-VERSIONING: Versionado de API
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "VERSION_PARAM": "version",
    # Throttling básico de sentido común. Ajusta según tus endpoints críticos.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": os.getenv("THROTTLE_USER", "100/min"),
        "anon": os.getenv("THROTTLE_ANON", "30/min"),
        
        # Scopes específicos
        "auth_login": os.getenv("THROTTLE_AUTH_LOGIN", "3/min"),
        "auth_verify": os.getenv("THROTTLE_AUTH_VERIFY", "3/10min"),
        "payments": os.getenv("THROTTLE_PAYMENTS", "30/min"),
        
        # Bot
        "bot": os.getenv("THROTTLE_BOT", "5/min"),
        "bot_daily": os.getenv("THROTTLE_BOT_DAILY", "100/day"),
        "bot_ip": os.getenv("THROTTLE_BOT_IP", "20/hour"),
        
        # Admin (NUEVO)
        "admin": os.getenv("THROTTLE_ADMIN", "1000/hour"),
        
        # Endpoints críticos adicionales
        "appointments_create": os.getenv("THROTTLE_APPT_CREATE", "10/hour"),
        "profile_update": os.getenv("THROTTLE_PROFILE_UPDATE", "20/hour"),
        "analytics_export": os.getenv("THROTTLE_ANALYTICS_EXPORT", "5/hour"),
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
# ZENZSPA-OPS-REDIS-TLS: Validar Redis TLS en producción
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1")
if not DEBUG:
    if not REDIS_URL.startswith("rediss://"):
        raise RuntimeError(
            "REDIS_URL debe usar rediss:// (TLS) en producción. "
            f"URL actual: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}"
        )

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # ZENZSPA-REDIS-WATCHDOG: No ignorar excepciones de Redis
            "IGNORE_EXCEPTIONS": False,
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
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# Credenciales para el asistente basado en Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# CORRECCIÓN CRÍTICA: Validar que la API key existe en producción
if not GEMINI_API_KEY and not DEBUG:
    raise RuntimeError(
        "GEMINI_API_KEY no configurada. El módulo bot requiere esta variable "
        "de entorno para funcionar en producción. Configure GEMINI_API_KEY en "
        "el archivo .env o como variable de entorno del sistema."
    )

# CORRECCIÓN MODERADA: Timeout aumentado de 10s a 20s para reducir errores en horarios pico
try:
    BOT_GEMINI_TIMEOUT = int(os.getenv("BOT_GEMINI_TIMEOUT", "20"))
except ValueError:
    BOT_GEMINI_TIMEOUT = 20

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

# ZENZSPA-WOMPI-REDIRECT: Validar HTTPS en producción
if not DEBUG:
    if not WOMPI_REDIRECT_URL.startswith("https://"):
        raise RuntimeError(
            f"WOMPI_REDIRECT_URL debe usar https:// en producción. URL actual: {WOMPI_REDIRECT_URL}"
        )
    # Validar que pertenezca a CORS_ALLOWED_ORIGINS
    wompi_origin = WOMPI_REDIRECT_URL.split("/")[0] + "//" + WOMPI_REDIRECT_URL.split("/")[2]
    if wompi_origin not in CORS_ALLOWED_ORIGINS:
        raise RuntimeError(
            f"WOMPI_REDIRECT_URL origin ({wompi_origin}) debe estar en CORS_ALLOWED_ORIGINS"
        )

# --------------------------------------------------------------------------------------
# CORS/CSRF
# --------------------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = os.getenv(
    "CORS_ALLOW_CREDENTIALS",
    "1" if DEBUG else "0",
) in ("1", "true", "True")
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

# ZENZSPA-SEC-COOKIE-SAMESITE: Configuración de cookies para SPA
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_HTTPONLY = False  # Debe ser False para que JavaScript pueda leerla
CSRF_COOKIE_SAMESITE = "None" if CORS_ALLOW_CREDENTIALS else "Lax"

# --------------------------------------------------------------------------------------
# Seguridad adicional en prod
# --------------------------------------------------------------------------------------
SECURE_SSL_REDIRECT = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ZENZSPA-SEC-PROXY-SSL: Configuración para balanceadores/proxies
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") in ("1", "true", "True")
if TRUST_PROXY:
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_REDIRECT_EXEMPT = _split_env("SECURE_REDIRECT_EXEMPT")

if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.getenv("HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --------------------------------------------------------------------------------------
# CSP (django-csp) V4.0+
# --------------------------------------------------------------------------------------
# ZENZSPA-CSP-CONNECT: Mejorar CSP con servicios externos
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'", "cdn.jsdelivr.net", "unpkg.com"],
        "style-src": ["'self'", "fonts.googleapis.com", "cdn.jsdelivr.net", "unpkg.com"],
        "img-src": ["'self'", "data:", "blob:", "https://production.wompi.co"],
        "font-src": ["'self'", "fonts.gstatic.com", "cdn.jsdelivr.net", "unpkg.com"],
        "connect-src": [
            "'self'", "wss:", "https://api.twilio.com", "https://production.wompi.co"
        ] + CORS_ALLOWED_ORIGINS,
    }
}

# CSP Reporting (opcional)
CSP_REPORT_URI = os.getenv("CSP_REPORT_URI", "")
if CSP_REPORT_URI:
    CONTENT_SECURITY_POLICY["DIRECTIVES"]["report-uri"] = [CSP_REPORT_URI]

# --------------------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")

# ZENZSPA-OPS-REDIS-TLS: Validar Celery broker TLS en producción
if not DEBUG:
    if not CELERY_BROKER_URL.startswith("rediss://"):
        raise RuntimeError(
            "CELERY_BROKER_URL debe usar rediss:// (TLS) en producción. "
            f"URL actual: {CELERY_BROKER_URL.split('@')[-1] if '@' in CELERY_BROKER_URL else CELERY_BROKER_URL}"
        )

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ZENZSPA-CELERYBEAT-ARTIFACTS: Mover schedule fuera del repo
CELERY_BEAT_SCHEDULE_FILENAME = os.getenv(
    "CELERY_BEAT_SCHEDULE_FILENAME",
    "/var/run/zenzspa/celerybeat-schedule" if not DEBUG else str(BASE_DIR / "celerybeat-schedule"),
)

# ZENZSPA-OPS-CELERY-HARDENING: Configuración robusta de Celery
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "120"))  # 2 minutos
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "100"))  # 100 segundos
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "500"))

# Rutas de tareas a colas dedicadas
CELERY_TASK_ROUTES = {
    "finances.tasks.run_developer_payout": {"queue": "payments"},
    "finances.tasks.*": {"queue": "payments"},
    "spa.tasks.*": {"queue": "appointments"},
    "notifications.tasks.*": {"queue": "notifications"},
    "bot.tasks.*": {"queue": "bot"},
}

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
    "bot-daily-token-report": {
        "task": "bot.tasks.report_daily_token_usage",
        "schedule": crontab(minute=0, hour=8),
    },
    "bot-cleanup-old-logs": {
        "task": "bot.tasks.cleanup_old_bot_logs",
        "schedule": crontab(minute=0, hour=3, day_of_week=0),
    },
    # Tareas de limpieza y mantenimiento
    "cleanup-idempotency-keys": {
        "task": "core.tasks.cleanup_old_idempotency_keys",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-user-sessions": {
        "task": "users.tasks.cleanup_inactive_sessions",
        "schedule": crontab(hour=4, minute=0),
    },
    "cleanup-kiosk-sessions": {
        "task": "profiles.tasks.cleanup_expired_kiosk_sessions",
        "schedule": crontab(hour=3, minute=30),
    },
    "cleanup-notification-logs": {
        "task": "notifications.tasks.cleanup_old_notification_logs",
        "schedule": crontab(hour=2, minute=0),
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

# Site URL for email notifications
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# ZENZSPA-OPS-SITE-URL: Validar SITE_URL y DEFAULT_FROM_EMAIL en producción
if not DEBUG:
    if not os.getenv("SITE_URL"):
        raise RuntimeError("SITE_URL debe estar configurado en producción.")
    if not SITE_URL.startswith("https://"):
        raise RuntimeError(
            f"SITE_URL debe usar https:// en producción. URL actual: {SITE_URL}"
        )
    # Validar que el dominio de SITE_URL esté en ALLOWED_HOSTS
    site_domain = SITE_URL.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    if site_domain not in ALLOWED_HOSTS:
        raise RuntimeError(
            f"El dominio de SITE_URL ({site_domain}) debe estar en ALLOWED_HOSTS"
        )
    
    if not os.getenv("DEFAULT_FROM_EMAIL"):
        raise RuntimeError("DEFAULT_FROM_EMAIL debe estar configurado en producción.")

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
            "()": "core.logging_filters.SanitizeAPIKeyFilter",
        },
        "sanitize_pii": {
            "()": "core.logging_filters.SanitizePIIFilter",
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
            "filename": BASE_DIR / "logs" / "zenzspa.log",
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
    
    # ZENZSPA-SENTRY-CELERY: Agregar integraciones completas
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
# ZENZSPA-NEWRELIC-CONFIG: Configuración mejorada de New Relic
NEW_RELIC_LICENSE_KEY = os.getenv("NEW_RELIC_LICENSE_KEY", "")
NEW_RELIC_CONFIG_FILE = os.getenv("NEW_RELIC_CONFIG_FILE", str(BASE_DIR / "newrelic.ini"))
if NEW_RELIC_LICENSE_KEY and not DEBUG:
    try:
        import newrelic.agent
        from pathlib import Path
        config_path = Path(NEW_RELIC_CONFIG_FILE)
        if config_path.exists():
            newrelic.agent.initialize(
                config_file=config_path,
                environment=os.getenv("NEW_RELIC_ENV", "production"),
            )
        else:
            import warnings
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
        # ZENZSPA-DEBUG-TOOLBAR: Soporte para IPv6 y Docker
        INTERNAL_IPS = _split_env("DEBUG_TOOLBAR_IPS", "127.0.0.1 ::1")
        
        DEBUG_TOOLBAR_CONFIG = {
            "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
            "SQL_WARNING_THRESHOLD": 100,  # 100ms
        }
    except ImportError:
        pass

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
