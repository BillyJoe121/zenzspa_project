import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


def log_performance(threshold_seconds=1.0):
    """
    Decorador para medir y registrar el tiempo de ejecución de métodos.
    
    Args:
        threshold_seconds: Tiempo mínimo (en segundos) para registrar una advertencia.
                          Por defecto 1.0 segundo.
    
    Usage:
        @log_performance(threshold_seconds=0.5)
        def expensive_method(self):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                
                # Siempre registrar en DEBUG
                logger.debug(
                    f"{func.__module__}.{func.__qualname__} took {duration:.3f}s"
                )
                
                # Advertir si excede el umbral
                if duration > threshold_seconds:
                    logger.warning(
                        f"SLOW QUERY: {func.__module__}.{func.__qualname__} "
                        f"took {duration:.3f}s (threshold: {threshold_seconds}s)"
                    )
        
        return wrapper
    return decorator
