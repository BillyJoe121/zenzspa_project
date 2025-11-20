import time
import logging
import uuid
import re
from contextlib import contextmanager
from difflib import SequenceMatcher
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class BotSecurityService:
    # --- CONFIGURACIÓN DE SEGURIDAD ---
    MAX_CHAR_LIMIT = 300
    BLOCK_DURATION = 60 * 60 * 24  # 24 Horas de castigo

    STRIKE_LIMIT = 3
    STRIKE_TIMEOUT = 60 * 30  # 30 min de "Probation"

    # Configuración Anti-Spam Avanzada
    SIMILARITY_THRESHOLD = 0.85  # 85% de similitud se considera repetición
    MAX_VELOCITY = 4  # Máximo 4 mensajes...
    VELOCITY_WINDOW = 60  # ... en 60 segundos

    HISTORY_LIMIT = 5  # Solo guardamos los últimos 5 mensajes para comparar

    def __init__(self, user):
        self.user = user
        self.user_id = user.id
        # Namespaces para Redis
        self.block_key = f"bot:block:{self.user_id}"
        self.strikes_key = f"bot:strikes:{self.user_id}"
        # Guardamos texto, no hash
        self.history_key = f"bot:history_txt:{self.user_id}"
        self.velocity_key = f"bot:velocity:{self.user_id}"

    def is_blocked(self) -> tuple[bool, str]:
        if cache.get(self.block_key):
            return True, "Acceso suspendido temporalmente (24h) por actividad inusual."
        return False, ""

    def validate_input_length(self, message: str) -> tuple[bool, str]:
        if len(message) > self.MAX_CHAR_LIMIT:
            return False, f"Mensaje muy largo. Máximo {self.MAX_CHAR_LIMIT} caracteres."
        return True, ""

    def validate_input_content(self, message: str) -> tuple[bool, str]:
        """
        CORRECCIÓN CRÍTICA: Detecta intentos de jailbreak/prompt injection.
        Busca patrones sospechosos que intentan modificar las instrucciones del bot.
        """
        JAILBREAK_PATTERNS = [
            r"ignora\s+(las\s+)?instrucciones",
            r"olvida\s+(las\s+)?instrucciones",
            r"nueva\s+instrucci[oó]n",
            r"eres\s+un\s+asistente\s+que",
            r"ahora\s+eres",
            r"system\s+prompt",
            r"api\s+key",
            r"prompt\s+injection",
            r"jailbreak",
            r"\[SYSTEM\]",
            r"\[ADMIN\]",
        ]
        
        message_lower = message.lower()
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.warning(
                    "Intento de jailbreak detectado para usuario %s: %s",
                    self.user_id, message[:100]
                )
                return False, "Mensaje sospechoso detectado. Por favor reformula tu pregunta."
        
        return True, ""

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

    def handle_off_topic(self) -> str:
        """Manejo de strikes por contenido no relacionado (Gemini)."""
        # Protegemos la lectura/escritura de strikes para evitar perder cuentas
        with self._lock("strikes"):
            current_strikes = cache.get(self.strikes_key, 0)
            new_strikes = current_strikes + 1

            if new_strikes >= self.STRIKE_LIMIT:
                logger.warning(
                    "Usuario %s bloqueado por contenido off-topic: %d strikes",
                    self.user_id, new_strikes
                )
                self._apply_ban()
                return "Has ignorado las advertencias repetidamente. Chat bloqueado por 24 horas."

            logger.info(
                "Usuario %s recibió strike %d/%d por contenido off-topic",
                self.user_id, new_strikes, self.STRIKE_LIMIT
            )
            cache.set(self.strikes_key, new_strikes,
                      timeout=self.STRIKE_TIMEOUT)
            return f"Por favor, mantengamos la conversación sobre los servicios del Spa. (Advertencia {new_strikes}/{self.STRIKE_LIMIT})"

    def _apply_ban(self):
        """Bloqueo duro de 24h y limpieza de trazas."""
        logger.warning(
            "Usuario %s bloqueado por 24h. Limpiando strikes/historial/velocidad.",
            self.user_id
        )
        cache.set(self.block_key, True, self.BLOCK_DURATION)
        cache.delete(self.strikes_key)
        cache.delete(self.history_key)
        cache.delete(self.velocity_key)
