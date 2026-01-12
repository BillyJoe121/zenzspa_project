import time
import logging
import uuid
from contextlib import contextmanager

from django.core.cache import cache

logger = logging.getLogger(__name__)


class LockingMixin:
    @contextmanager
    def _lock(self, name):
        """
        CORRECCIÓN CRÍTICA: Spinlock distribuido con UUID para ownership.
        Evita race conditions y locks zombies mediante validación de ownership.
        
        Mejoras implementadas:
        - UUID único por lock para evitar que dos procesos piensen que tienen el lock
        - Timeout reducido a 3s (antes 5s) para minimizar locks zombies
        - Validación de ownership antes de liberar el lock
        - Acquire timeout de 2s para evitar esperas infinitas
        """
        lock_key = f"bot:lock:{self.user_id}:{name}"
        lock_value = str(uuid.uuid4())  # Identificador único de este proceso
        lock_timeout = 3  # Timeout del lock en cache (reducido de 5s)
        acquire_timeout = 2.0  # Tiempo máximo intentando adquirir
        timeout_at = time.time() + acquire_timeout
        acquired = False

        try:
            while time.time() < timeout_at:
                # cache.add funciona como SETNX (Set if Not Exists) atómico
                if cache.add(lock_key, lock_value, timeout=lock_timeout):
                    acquired = True
                    break
                time.sleep(0.05)  # Espera breve antes de reintentar
            
            if not acquired:
                # Si no logramos el lock, fallamos ruidosamente para no corromper datos
                raise BlockingIOError(f"No se pudo adquirir el lock para {name}")
            
            yield
        finally:
            if acquired:
                # CORRECCIÓN CRÍTICA: Solo borrar si el valor coincide
                # Esto evita borrar el lock de otro proceso que lo adquirió después
                current_value = cache.get(lock_key)
                if current_value == lock_value:
                    cache.delete(lock_key)
                else:
                    # El lock expiró y otro proceso lo tomó, no hacer nada
                    logger.warning(
                        "Lock para %s expiró antes de liberarse. Usuario: %s",
                        name, self.user_id
                    )
