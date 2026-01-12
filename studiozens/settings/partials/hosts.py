import os
import sys

from .core import DEBUG, _split_env

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
