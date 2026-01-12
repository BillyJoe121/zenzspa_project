import os

from .core import DEBUG
from .hosts import ALLOWED_HOSTS

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
