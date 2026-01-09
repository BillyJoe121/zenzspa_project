import time
import logging
from difflib import SequenceMatcher

from django.core.cache import cache

logger = logging.getLogger(__name__)


class RateLimitMixin:
    def check_velocity(self) -> bool:
        """
        Filtro 1: VELOCIDAD.
        Evita que alguien envíe mensajes distintos pero muy rápido para quemar tokens.
        Protegido con Lock para evitar condiciones de carrera.
        """
        with self._lock("velocity"):
            # Obtenemos la lista de timestamps de los mensajes recientes
            timestamps = cache.get(self.velocity_key, [])
            now = time.time()

            # Filtramos solo los timestamps que están dentro de la ventana (últimos 60s)
            recent_timestamps = [
                t for t in timestamps if now - t < self.VELOCITY_WINDOW]

            # Si hay más mensajes de los permitidos en la ventana de tiempo
            if len(recent_timestamps) >= self.MAX_VELOCITY:
                logger.warning(
                    "Usuario %s bloqueado por velocidad: %d mensajes en %ds",
                    self.user_id, len(recent_timestamps), self.VELOCITY_WINDOW
                )
                self._apply_ban()
                return True  # Bloqueado por velocidad

            # Agregamos el actual y guardamos
            recent_timestamps.append(now)
            cache.set(self.velocity_key, recent_timestamps,
                      self.VELOCITY_WINDOW)
            return False

    def check_repetition(self, message: str) -> bool:
        """
        Filtro 2: SIMILITUD (Fuzzy Matching).
        Compara el mensaje actual con los últimos 5. Si se parece mucho, cuenta como repetido.
        Protegido con Lock para consistencia en la lista histórica.
        """
        with self._lock("history"):
            clean_msg = message.strip().lower()

            # Historial guarda tuplas: (texto_mensaje, contador_repeticiones)
            history = cache.get(self.history_key, [])

            is_repeated = False

            # Recorremos el historial reciente para buscar similitudes
            for i, (past_msg, count) in enumerate(history):
                # Usamos SequenceMatcher para ver qué tan parecidos son (0 a 1)
                similarity = SequenceMatcher(None, clean_msg, past_msg).ratio()

                if similarity >= self.SIMILARITY_THRESHOLD:
                    # ¡Es el "mismo" mensaje!
                    new_count = count + 1
                    history[i] = (past_msg, new_count)  # Actualizamos contador

                    if new_count >= 3:  # Límite de repeticiones similares
                        logger.warning(
                            "Usuario %s bloqueado por repetición: mensaje '%s' repetido %d veces",
                            self.user_id, past_msg[:50], new_count
                        )
                        self._apply_ban()
                        return True

                    is_repeated = True
                    break  # Ya encontramos el repetido, dejamos de buscar

            if not is_repeated:
                # Si no se parece a ninguno, lo agregamos como nuevo
                history.append((clean_msg, 1))

            # Mantenemos solo los últimos N mensajes para no llenar la memoria
            # Y refrescamos el TTL (Time To Live)
            cache.set(self.history_key, history[-self.HISTORY_LIMIT:], 60 * 60)

            return False
