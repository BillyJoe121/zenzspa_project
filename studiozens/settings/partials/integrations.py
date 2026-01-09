import os

from .core import DEBUG, _parse_action_scores, _split_env
from .hosts import CORS_ALLOWED_ORIGINS

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
# Wompi Payouts API (Pagos a Terceros)
WOMPI_PAYOUT_MODE = os.getenv("WOMPI_PAYOUT_MODE", "sandbox")  # 'sandbox' o 'production'

# Credenciales según el modo
if WOMPI_PAYOUT_MODE == "sandbox":
    WOMPI_PAYOUT_PRIVATE_KEY = os.getenv("WOMPI_PAYOUT_SANDBOX_API_KEY", "")
    WOMPI_PAYOUT_USER_ID = os.getenv("WOMPI_PAYOUT_SANDBOX_USER_ID", "")
    WOMPI_PAYOUT_BASE_URL = os.getenv(
        "WOMPI_PAYOUT_SANDBOX_BASE_URL",
        "https://sandbox.api.payouts.wompi.co/v1"
    )
    WOMPI_PAYOUT_EVENTS_SECRET = os.getenv("WOMPI_PAYOUT_SANDBOX_EVENTS_SECRET", "")
else:  # production
    WOMPI_PAYOUT_PRIVATE_KEY = os.getenv("WOMPI_PAYOUT_PROD_API_KEY", "")
    WOMPI_PAYOUT_USER_ID = os.getenv("WOMPI_PAYOUT_PROD_USER_ID", "")
    WOMPI_PAYOUT_BASE_URL = os.getenv(
        "WOMPI_PAYOUT_PROD_BASE_URL",
        "https://api.payouts.wompi.co/v1"
    )
    WOMPI_PAYOUT_EVENTS_SECRET = os.getenv("WOMPI_PAYOUT_PROD_EVENTS_SECRET", "")

# Configuración del desarrollador (beneficiario de comisiones)
WOMPI_DEVELOPER_DESTINATION = os.getenv("WOMPI_DEVELOPER_DESTINATION", "")
WOMPI_DEVELOPER_LEGAL_ID_TYPE = os.getenv("WOMPI_DEVELOPER_LEGAL_ID_TYPE", "CC")
WOMPI_DEVELOPER_LEGAL_ID = os.getenv("WOMPI_DEVELOPER_LEGAL_ID", "")
WOMPI_DEVELOPER_BANK_ID = os.getenv("WOMPI_DEVELOPER_BANK_ID", "1007")  # Default: Bancolombia
WOMPI_DEVELOPER_ACCOUNT_TYPE = os.getenv("WOMPI_DEVELOPER_ACCOUNT_TYPE", "AHORROS")
WOMPI_DEVELOPER_ACCOUNT_NUMBER = os.getenv("WOMPI_DEVELOPER_ACCOUNT_NUMBER", "")
WOMPI_DEVELOPER_NAME = os.getenv("WOMPI_DEVELOPER_NAME", "")
WOMPI_DEVELOPER_EMAIL = os.getenv("WOMPI_DEVELOPER_EMAIL", "")

# Configuración operativa de Payouts
WOMPI_PAYOUT_PAYMENT_TYPE = os.getenv("WOMPI_PAYOUT_PAYMENT_TYPE", "OTHER")  # PAYROLL, PROVIDERS, OTHER
WOMPI_CURRENCY = os.getenv("WOMPI_CURRENCY", "COP")

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
