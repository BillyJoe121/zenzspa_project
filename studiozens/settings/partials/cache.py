import os

from .core import DEBUG

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
