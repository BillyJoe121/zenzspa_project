"""
Rate limiting helpers for Gemini API calls.
"""
import time
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Rate limit para Gemini API (plan gratuito: 15 RPM)
GEMINI_RATE_LIMIT_KEY = "gemini_api_rate_limit"
GEMINI_MAX_REQUESTS_PER_MINUTE = 15


def check_rate_limit():
    """
    Verifica si podemos hacer una request a Gemini sin exceder el límite.
    Usa una ventana deslizante de 60 segundos.

    Returns:
        tuple: (can_proceed: bool, wait_seconds: int)
    """
    now = time.time()
    window_start = now - 60  # Ventana de 1 minuto

    # Obtener timestamps de requests recientes
    recent_requests = cache.get(GEMINI_RATE_LIMIT_KEY, [])

    # Filtrar solo los del último minuto
    recent_requests = [ts for ts in recent_requests if ts > window_start]

    if len(recent_requests) < GEMINI_MAX_REQUESTS_PER_MINUTE:
        # Hay espacio, agregar timestamp actual
        recent_requests.append(now)
        cache.set(GEMINI_RATE_LIMIT_KEY, recent_requests, 70)  # TTL 70s por seguridad
        return True, 0
    else:
        # Límite alcanzado, calcular cuánto esperar
        oldest_request = min(recent_requests)
        wait_seconds = int(oldest_request + 60 - now) + 1
        return False, wait_seconds


# Compat alias for existing imports
_check_rate_limit = check_rate_limit

__all__ = [
    "check_rate_limit",
    "_check_rate_limit",
    "GEMINI_RATE_LIMIT_KEY",
    "GEMINI_MAX_REQUESTS_PER_MINUTE",
]
