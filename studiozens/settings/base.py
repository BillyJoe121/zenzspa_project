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
    }

    # Validar DB: Si tenemos DATABASE_URL, no exigimos DB_PASSWORD por separado
    if not os.getenv("DATABASE_URL") and not os.getenv("DB_PASSWORD"):
        required_vars["DB_PASSWORD"] = "Contraseña de base de datos (o DATABASE_URL)"

    # En producción, validar más variables
    if os.getenv("DEBUG", "0") not in ("1", "true", "True"):
        required_vars.update({
            "TWILIO_ACCOUNT_SID": "Twilio Account SID",
            "TWILIO_AUTH_TOKEN": "Twilio Auth Token",
            "TWILIO_VERIFY_SERVICE_SID": "Twilio Verify Service SID",
            "WOMPI_PUBLIC_KEY": "Wompi Public Key",
            "WOMPI_PRIVATE_KEY": "Wompi Private Key",
            "WOMPI_INTEGRITY_SECRET": "Wompi Integrity Secret",
            "WOMPI_EVENT_SECRET": "Wompi Event Secret",
            "WOMPI_PAYOUT_PRIVATE_KEY": "Wompi Payout Private Key",
            "WOMPI_PAYOUT_BASE_URL": "Wompi Payout Base URL",
            "WOMPI_DEVELOPER_DESTINATION": "Destino de dispersión para desarrollador",
            "GEMINI_API_KEY": "Gemini API Key para bot",
            "REDIS_URL": "URL de Redis",
            # CELERY_BROKER_URL: Opcional si REDIS_URL está presente (usamos Redis como broker por default)
            "EMAIL_HOST_USER": "Usuario de email",
            "EMAIL_HOST_PASSWORD": "Contraseña de email",
        })
        
        # Validación lógica condicional para Celery
        if not os.getenv("CELERY_BROKER_URL") and not os.getenv("REDIS_URL"):
             required_vars["CELERY_BROKER_URL"] = "URL del broker de Celery (o REDIS_URL)"

    missing = []
    # Verificar solo las que quedaron en el diccionario
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({description})")

    if missing:
        raise RuntimeError(
            "Variables de entorno faltantes:\n"
            + "\n".join(f"  - {var}" for var in missing)
            + "\n\nConfigura estas variables en el archivo .env o como variables de entorno del sistema."
        )


# Validar variables al inicio
validate_required_env_vars()

# --------------------------------------------------------------------------------------
# Paths básicos
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --------------------------------------------------------------------------------------
# Claves y modo
# --------------------------------------------------------------------------------------
# Admite rotación de llaves secretas (Django 5.2+)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no configurada. Define la variable de entorno antes de iniciar la aplicación.")

# Configuración de encriptación Fernet para datos sensibles (HIPAA/GDPR Compliance)
def _load_fernet_keys():
    """
    Permite rotación: FERNET_KEYS="key_actual,key_anterior" (la primera se usa para cifrar).
    Si no hay lista, usa FERNET_KEY.
    """
    keys: list[bytes] = []
    raw_list = os.getenv("FERNET_KEYS", "")
    for chunk in raw_list.replace(",", " ").split():
        if chunk.strip():
            keys.append(chunk.strip().encode())
    single = os.getenv("FERNET_KEY")
    if single:
        keys.append(single.encode())
    return [k for k in keys if k]


FERNET_KEYS = _load_fernet_keys()
if not FERNET_KEYS:
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


# Para cambiar de red WiFi, actualiza la IP aquí (solo aplica si no usas Docker)
# Nueva WiFi (192.168.1.x):
# ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS", "localhost 127.0.0.1 testserver web 192.168.1.14")
# CSRF_TRUSTED_ORIGINS = _split_env(
#     "CSRF_TRUSTED_ORIGINS",
#     "http://localhost http://127.0.0.1 http://localhost:3000 http://127.0.0.1:3000 http://localhost:8000 http://127.0.0.1:8000 http://192.168.1.14:3000 http://192.168.1.14:8000",
# )
# CORS_ALLOWED_ORIGINS = _split_env(
#     "CORS_ALLOWED_ORIGINS",
#     "http://localhost:3000 http://127.0.0.1:3000 http://localhost:3001 http://127.0.0.1:3001 http://192.168.1.14:3000",
# )
# WiFi actual (192.168.40.x):
ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS", "localhost 127.0.0.1 testserver web 192.168.40.81")

# Debug: Imprimir ALLOWED_HOSTS para verificar configuración
import sys
if not DEBUG:
    print(f"DEBUG: ALLOWED_HOSTS configurado: {ALLOWED_HOSTS}", file=sys.stderr)
    print(f"DEBUG: Variable ALLOWED_HOSTS env: {os.getenv('ALLOWED_HOSTS', 'NO CONFIGURADA')}", file=sys.stderr)
CSRF_TRUSTED_ORIGINS = _split_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost http://127.0.0.1 http://localhost:3000 http://127.0.0.1:3000 http://localhost:8000 http://127.0.0.1:8000 http://192.168.40.81:3000 http://192.168.40.81:8000",
)
CORS_ALLOWED_ORIGINS = _split_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000 http://127.0.0.1:3000 http://localhost:3001 http://127.0.0.1:3001 http://192.168.40.81:3000",
)

# Configuraciones de cookies y CSRF para desarrollo
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_USE_SESSIONS = False  # Asegura que CSRF use cookies, no sesiones
    CSRF_COOKIE_NAME = 'csrftoken'  # Nombre estándar
    # TEMPORAL: Deshabilitar CSRF para admin en desarrollo
    # Nueva WiFi (192.168.1.x): CSRF_TRUSTED_ORIGINS.extend(['http://localhost:8000', 'http://127.0.0.1:8000', 'http://192.168.1.14:3000', 'http://192.168.1.14:8000'])
    # WiFi actual (192.168.40.x):
    CSRF_TRUSTED_ORIGINS.extend(['http://localhost:8000', 'http://127.0.0.1:8000', 'http://192.168.40.81:3000', 'http://192.168.40.81:8000'])
else:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Strict'
    SESSION_COOKIE_SAMESITE = 'Strict'

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
    "django_prometheus",

    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",                  # CORS
    "csp",                   # Content Security Policy
    "simple_history",
    "django_filters",              # Django Filter para búsquedas avanzadas
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
    "legal",
    "blog",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # CORS antes de CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "users.middleware.BlockedDeviceMiddleware",  # Bloqueo de dispositivos
    "profiles.middleware.KioskFlowEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "core.middleware.RequestIDMiddleware",
    "core.middleware.AdminAuditMiddleware",
    "core.middleware.PerformanceLoggingMiddleware",  # NUEVO - Logging de performance
    "django_prometheus.middleware.PrometheusAfterMiddleware",
    "legal.middleware.LegalConsentRequiredMiddleware",  # Enforce re-aceptación de términos
    # "axes.middleware.AxesMiddleware",               # Habilita si usas django-axes
]

# --------------------------------------------------------------------------------------
# Performance Monitoring
# --------------------------------------------------------------------------------------
SLOW_REQUEST_THRESHOLD = float(os.getenv("SLOW_REQUEST_THRESHOLD", "1.0"))  # segundos

ROOT_URLCONF = "studiozens.urls"

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

WSGI_APPLICATION = "studiozens.wsgi.application"

# --------------------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------------------
import dj_database_url
from urllib.parse import quote_plus

DATABASES = {}

if os.getenv("DATABASE_URL"):
    # Producción / Render (con URL completa)
    try:
        DATABASES["default"] = dj_database_url.config(
            conn_max_age=60,  # Reducido para mejor compatibilidad con Supabase pooler
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
        # Añadir opciones de timeout para evitar conexiones colgadas
        DATABASES["default"]["OPTIONS"] = DATABASES["default"].get("OPTIONS", {})
        DATABASES["default"]["OPTIONS"].update({
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",  # 30 segundos max por query
        })
    except Exception as e:
        # Si DATABASE_URL falla, intentar con variables individuales
        print(f"Warning: DATABASE_URL parsing failed: {e}")
        print("Falling back to individual DB environment variables")

        db_password = os.getenv("DB_PASSWORD", "")
        # URL-encode the password if it contains special characters
        encoded_password = quote_plus(db_password) if db_password else ""

        DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "studiozens"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": db_password,
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
            "OPTIONS": {
                "sslmode": os.getenv("DB_SSLMODE", "require"),
                "connect_timeout": 10,
                "client_encoding": "UTF8",
            },
        }
else:
    # Desarrollo local (variables individuales)
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "studiozens"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "sslmode": os.getenv("DB_SSLMODE", "require" if not DEBUG else "disable"),
            "connect_timeout": 10,
            "client_encoding": "UTF8",
        },
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
    # STUDIOZENS-API-VERSIONING: Versionado de API
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
        "user": os.getenv("THROTTLE_USER", "1000/min"),
        "anon": os.getenv("THROTTLE_ANON", "300/min"),

        # Scopes específicos de autenticación
        "auth_login": os.getenv("THROTTLE_AUTH_LOGIN", "30/min"),
        "auth_verify": os.getenv("THROTTLE_AUTH_VERIFY", "30/10min"),
        "password_change": os.getenv("THROTTLE_PASSWORD_CHANGE", "10/hour"),  # Protección anti brute-force
        "payments": os.getenv("THROTTLE_PAYMENTS", "100/min"),

        # Bot
        "bot": os.getenv("THROTTLE_BOT", "60/min"),
        "bot_daily": os.getenv("THROTTLE_BOT_DAILY", "500/day"),
        "bot_ip": os.getenv("THROTTLE_BOT_IP", "120/hour"),

        # Admin (NUEVO)
        "admin": os.getenv("THROTTLE_ADMIN", "5000/hour"),

        # Analytics (NUEVO)
        "analytics": os.getenv("THROTTLE_ANALYTICS", "60/minute"),
        "analytics_export": os.getenv("THROTTLE_ANALYTICS_EXPORT", "20/minute"),

        # Endpoints críticos adicionales
        "appointments_create": os.getenv("THROTTLE_APPT_CREATE", "120/hour"),
        "profile_update": os.getenv("THROTTLE_PROFILE_UPDATE", "60/hour"),
    },
}

# --------------------------------------------------------------------------------------
# Simple JWT
# --------------------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MIN", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "90"))),
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
# STUDIOZENS-OPS-REDIS-TLS: Validar Redis TLS en producción
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
            # CRÍTICO: Ignorar excepciones para evitar que requests se cuelguen
            # si Redis está lento o temporalmente no disponible
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 5,  # segundos
            "SOCKET_TIMEOUT": 5,
        },
        "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "300")),
    }
}
# Usar cached_db para mayor resiliencia: guarda en DB, cachea en Redis
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
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
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Número para SMS/llamadas
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")  # Legacy
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")  # Número WhatsApp Business

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
WOMPI_PRIVATE_KEY = os.getenv("WOMPI_PRIVATE_KEY", "")
WOMPI_INTEGRITY_SECRET = os.getenv("WOMPI_INTEGRITY_SECRET", "")
# Alias compatible con la documentación más reciente.
WOMPI_INTEGRITY_KEY = os.getenv("WOMPI_INTEGRITY_KEY", WOMPI_INTEGRITY_SECRET)
WOMPI_EVENT_SECRET = os.getenv("WOMPI_EVENT_SECRET", "")
WOMPI_BASE_URL = os.getenv("WOMPI_BASE_URL", "https://sandbox.wompi.co/v1")
WOMPI_ACCEPTANCE_TOKEN = os.getenv("WOMPI_ACCEPTANCE_TOKEN", "")
WOMPI_REDIRECT_URL = os.getenv(
    "WOMPI_REDIRECT_URL", "http://localhost:3000/payment-result")
WOMPI_PAYOUT_PRIVATE_KEY = os.getenv("WOMPI_PAYOUT_PRIVATE_KEY", "")
WOMPI_PAYOUT_BASE_URL = os.getenv("WOMPI_PAYOUT_BASE_URL", "")
WOMPI_DEVELOPER_DESTINATION = os.getenv("WOMPI_DEVELOPER_DESTINATION", "")

# STUDIOZENS-WOMPI-REDIRECT: Validar HTTPS en producción
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
    "DEFAULT_FROM_EMAIL", "StudioZens <no-reply@studiozens.com>")

# Site URL for email notifications
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# STUDIOZENS-OPS-SITE-URL: Validar SITE_URL y DEFAULT_FROM_EMAIL en producción
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
