from __future__ import annotations
from typing import Any, Callable, Optional, TypeVar, Tuple, List, Iterable
from functools import lru_cache, wraps
from django.utils.timezone import now
from django.core.cache import cache
from django.http import HttpRequest
from django.conf import settings
from zoneinfo import ZoneInfo
import time
import logging
from datetime import datetime

try:
    from prometheus_client import Counter
except ImportError:
    Counter = None

logger = logging.getLogger(__name__)

T = TypeVar("T")

BOGOTA_TZ = ZoneInfo("America/Bogota")

def utc_now() -> Any:
    """Retorna el timestamp aware en UTC (alias de django.utils.timezone.now)."""
    return now()

def to_bogota(dt: Optional[datetime]) -> Optional[datetime]:
    """Convierte un datetime aware a zona America/Bogota si existe."""
    if not dt:
        return dt
    return dt.astimezone(BOGOTA_TZ)

def get_client_ip(request: HttpRequest) -> str:
    """
    Obtiene la IP del cliente respetando la configuración de proxy.

    Si TRUST_PROXY=True en settings, honra X-Forwarded-For (primer IP).
    Si TRUST_PROXY=False o no está configurado, usa REMOTE_ADDR directamente.

    Esto previene spoofing de IP en ambientes donde no hay proxy confiable.
    """
    trust_proxy = getattr(settings, 'TRUST_PROXY', False)

    if trust_proxy:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            # Tomar la primera IP (cliente original)
            return xff.split(",")[0].strip()

    # Fallback a REMOTE_ADDR (IP directa de la conexión)
    return request.META.get("REMOTE_ADDR", "")

def cached_singleton(key: str, timeout: int, loader: Callable[[], T]) -> T:
    """Obtiene un valor de caché y si no existe lo calcula y guarda."""
    value = cache.get(key)
    if value is None:
        value = loader()
        cache.set(key, value, timeout=timeout)
    return value

def invalidate(key: str):
    """Elimina una clave de caché si existe."""
    cache.delete(key)


def emit_metric(name: str, value: float = 1, tags: Optional[dict] = None) -> None:
    """
    Emite una métrica en formato log estructurado para recolectores externos (Prometheus/statsd por sidecar).

    Args:
        name: nombre de la métrica, ej: "booking.conflict"
        value: valor numérico (counter/gauge)
        tags: diccionario opcional de etiquetas
    """
    tags = tags or {}
    # Prometheus counter si está disponible
    if Counter:
        try:
            label_names = sorted(tags.keys())
            key = (name, tuple(label_names))
            if not hasattr(emit_metric, "_counters"):
                emit_metric._counters = {}
            counters = emit_metric._counters
            if key not in counters:
                counters[key] = Counter(name.replace(".", "_"), name, label_names)
            counter = counters[key]
            counter.labels(**{k: str(tags[k]) for k in label_names}).inc(value)
            return
        except Exception:
            # Fallback a logging si algo falla
            pass

    try:
        logger.info(
            "metric",
            extra={
                "metric_name": name,
                "metric_value": value,
                "metric_tags": tags,
            },
        )
    except Exception:
        return None

def safe_audit_log(action: str, admin_user=None, target_user=None, target_appointment=None, details: Any = None):
    """
    Escribe AuditLog tolerante a errores y a importaciones circulares.
    """
    try:
        from .models import AuditLog  # import local para evitar ciclos
        entry = AuditLog.objects.create(
            action=action,
            admin_user=admin_user,
            target_user=target_user,
            target_appointment=target_appointment,
            details=details or "",
        )
        return entry
    except Exception:
        return None


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
    """
    Decorator que reintenta una función con exponential backoff.
    
    Args:
        max_retries: Número máximo de reintentos
        base_delay: Delay inicial en segundos
        max_delay: Delay máximo en segundos
    
    Ejemplo:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def call_external_api():
            # código que puede fallar
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Intento {attempt + 1}/{max_retries} falló para {func.__name__}: {e}. "
                            f"Reintentando en {delay}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * 2, max_delay)  # Exponential backoff
                    else:
                        logger.error(
                            f"Todos los intentos fallaron para {func.__name__}: {e}"
                        )
            
            raise last_exception
        return wrapper
    return decorator


def batch_process(items: List[T], batch_size: int, processor: Callable[[List[T]], Any]) -> List[Any]:
    """
    Procesa items en lotes para optimizar performance.
    
    Args:
        items: Lista de items a procesar
        batch_size: Tamaño de cada lote
        processor: Función que procesa un lote
    
    Returns:
        Lista de resultados de cada lote
    
    Ejemplo:
        def process_batch(users):
            User.objects.bulk_update(users, ['is_active'])
        
        results = batch_process(users, batch_size=100, processor=process_batch)
    """
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        try:
            result = processor(batch)
            results.append(result)
        except Exception as e:
            logger.error(f"Error procesando lote {i//batch_size + 1}: {e}")
            results.append(None)
    
    return results


def format_cop(amount: float | int) -> str:
    """
    Formatea un monto en pesos colombianos.
    
    Args:
        amount: Monto a formatear
    
    Returns:
        String formateado (ej: "$1.234.567")
    
    Ejemplo:
        >>> format_cop(1234567)
        '$1.234.567'
        >>> format_cop(1000.50)
        '$1.001'
    """
    try:
        # Redondear a entero (COP no usa decimales)
        amount_int = int(round(amount))
        # Formatear con separador de miles
        formatted = f"{amount_int:,}".replace(",", ".")
        return f"${formatted}"
    except (ValueError, TypeError):
        return "$0"


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Trunca un string a una longitud máxima.
    
    Args:
        text: Texto a truncar
        max_length: Longitud máxima
        suffix: Sufijo a agregar si se trunca
    
    Returns:
        Texto truncado
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix
