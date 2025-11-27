import os

from .base import (
    DEBUG,
    ALLOWED_HOSTS,
    CORS_ALLOWED_ORIGINS,
    CSRF_TRUSTED_ORIGINS,
    _split_env,
)

# Validar CORS/CSRF en producción
if not DEBUG:
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
if os.getenv("CSP_REPORT_URI"):
    CONTENT_SECURITY_POLICY["DIRECTIVES"]["report-uri"] = [os.getenv("CSP_REPORT_URI")]

# Alias utilizado por algunos tests/documentación
CSP_DIRECTIVES = CONTENT_SECURITY_POLICY["DIRECTIVES"]
