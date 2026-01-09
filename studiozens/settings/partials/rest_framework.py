import os

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
