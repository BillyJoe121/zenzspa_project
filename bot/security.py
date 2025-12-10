import time
import logging
import uuid
import re
from contextlib import contextmanager
from difflib import SequenceMatcher
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


def sanitize_for_logging(text: str, max_length: int = 100) -> str:
    """
    MEJORA #6: Sanitiza texto para logging seguro.

    Remueve caracteres de control que podrían causar log injection
    y trunca el texto para evitar logs excesivamente largos.

    Args:
        text: Texto a sanitizar
        max_length: Longitud máxima del texto (default: 100)

    Returns:
        str: Texto sanitizado y truncado
    """
    if not text:
        return ""

    # Remover caracteres de control (excepto espacios, tabs, newlines normales)
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # Reemplazar saltos de línea y tabs por espacios para logs de una línea
    sanitized = sanitized.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Comprimir múltiples espacios en uno solo
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Truncar si es muy largo
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized.strip()


def anonymize_pii(text: str, max_length: int = 200) -> str:
    """
    Remueve patrones típicos de PII (emails, teléfonos, direcciones) antes de enviarlos al LLM.
    """
    if not text:
        return ""
    # Quitar emails
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[email]", text)
    # Quitar números con 7+ dígitos (teléfonos)
    text = re.sub(r"\\b\\d{7,15}\\b", "[phone]", text)
    # Quitar direcciones comunes
    text = re.sub(r"(calle|cra|carrera|avenida|av|cll|diag|trans|transversal)\\s+[^\\s,]{1,50}", "[address]", text, flags=re.IGNORECASE)
    return sanitize_for_logging(text, max_length=max_length)


class BotSecurityService:
    # --- CONFIGURACIÓN DE SEGURIDAD ---
    MAX_CHAR_LIMIT = 300
    BLOCK_DURATION = 60 * 60 * 24  # 24 Horas de castigo

    STRIKE_LIMIT = 3
    STRIKE_TIMEOUT = 60 * 30  # 30 min de "Probation"

    # Configuración Anti-Spam Avanzada
    SIMILARITY_THRESHOLD = 0.85  # 85% de similitud se considera repetición
    MAX_VELOCITY = 10  # Máximo 10 mensajes...
    VELOCITY_WINDOW = 60  # ... en 60 segundos

    HISTORY_LIMIT = 5  # Solo guardamos los últimos 5 mensajes para comparar

    def __init__(self, user_or_id):
        """
        Inicializa el servicio de seguridad.

        Args:
            user_or_id: Puede ser un objeto User, un user_id (int), o un string
                        identificador (ej: "anon_123" para usuarios anónimos)
        """
        # Determinar si es un objeto User o un ID
        if hasattr(user_or_id, 'id'):
            # Es un objeto User
            self.user = user_or_id
            self.user_id = user_or_id.id
        else:
            # Es un ID directo (int o string)
            self.user = None
            self.user_id = user_or_id

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

        MEJORA #5: Incluye validación de delimitadores para prevenir inyección.
        """
        # Strings prohibidos explícitamente (delimitadores del prompt)
        FORBIDDEN_STRINGS = [
            "[INICIO_MENSAJE_USUARIO]",
            "[FIN_MENSAJE_USUARIO]",
            "[SYSTEM]",
            "[ADMIN]",
        ]

        # Verificar strings prohibidos primero (case-sensitive para delimitadores)
        for forbidden in FORBIDDEN_STRINGS:
            if forbidden in message:
                logger.warning(
                    "Intento de inyección de delimitadores para usuario %s",
                    self.user_id
                )
                return False, "Mensaje contiene caracteres no permitidos."

        # Patrones de jailbreak (case-insensitive)
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
        ]

        message_lower = message.lower()
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.warning(
                    "Intento de jailbreak detectado para usuario %s: %s",
                    self.user_id, sanitize_for_logging(message)
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

    def check_daily_limit(self, ip_address: str = None) -> tuple[bool, str]:
        """
        Verifica si el usuario ha excedido el límite diario de mensajes.
        Implementa límite dual:
        - Por usuario: 30 mensajes/día
        - Por IP: 50 mensajes/día (permite redes compartidas)
        
        El límite se reinicia a las 12:00 AM hora de Colombia (UTC-5).
        
        Args:
            ip_address: Dirección IP del cliente (opcional pero recomendado)
        
        Returns:
            tuple[bool, str]: (excedió_límite, mensaje_error)
        """
        from datetime import datetime, timedelta
        import pytz
        
        DAILY_LIMIT_USER = 30
        DAILY_LIMIT_IP = 50
        colombia_tz = pytz.timezone('America/Bogota')
        
        # Obtener la fecha actual en Colombia
        now_colombia = datetime.now(colombia_tz)
        today_key = now_colombia.strftime('%Y-%m-%d')
        
        # Calcular segundos hasta la medianoche de Colombia
        midnight_colombia = (now_colombia + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds_until_midnight = int((midnight_colombia - now_colombia).total_seconds())
        
        # 1. Verificar límite por IP (si se proporciona)
        if ip_address:
            ip_key = f"bot:daily_count_ip:{ip_address}:{today_key}"
            ip_count = cache.get(ip_key, 0)
            
            if ip_count >= DAILY_LIMIT_IP:
                logger.warning(
                    "IP %s alcanzó límite diario: %d/%d mensajes",
                    ip_address, ip_count, DAILY_LIMIT_IP
                )
                return True, "Has alcanzado el límite diario de mensajes desde esta red. El límite se reinicia a las 12:00 AM. Por favor, intenta mañana o agenda una cita directamente."
            
            # Incrementar contador de IP
            cache.set(ip_key, ip_count + 1, timeout=seconds_until_midnight)
        
        # 2. Verificar límite por usuario
        user_key = f"bot:daily_count:{self.user_id}:{today_key}"
        user_count = cache.get(user_key, 0)
        
        if user_count >= DAILY_LIMIT_USER:
            logger.warning(
                "Usuario %s alcanzó límite diario: %d/%d mensajes",
                self.user_id, user_count, DAILY_LIMIT_USER
            )
            return True, "Has alcanzado el límite diario de mensajes. El límite se reinicia a las 12:00 AM. Por favor, intenta mañana o agenda una cita directamente."
        
        # Incrementar contador de usuario
        new_user_count = user_count + 1
        cache.set(user_key, new_user_count, timeout=seconds_until_midnight)
        
        logger.info(
            "Usuario %s (IP: %s): mensaje %d/%d del día (IP: %d/%d)",
            self.user_id, ip_address or "N/A", 
            new_user_count, DAILY_LIMIT_USER,
            cache.get(f"bot:daily_count_ip:{ip_address}:{today_key}", 0) if ip_address else 0,
            DAILY_LIMIT_IP
        )
        
        return False, ""

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

        # Notificar al usuario sobre el bloqueo
        if self.user:
            try:
                from notifications.services import NotificationService
                NotificationService.send_notification(
                    user=self.user,
                    event_code="BOT_AUTO_BLOCK",
                    context={
                        "user_name": self.user.first_name,
                        "block_duration_hours": str(int(self.BLOCK_DURATION / 3600)),
                        "reason": "Incumplimiento de normas de uso del chat."
                    }
                )
            except Exception:
                logger.exception("Error enviando notificación de bloqueo a usuario %s", self.user_id)

    def block_user(self, reason: str = "Bloqueo manual"):
        """Bloquea al usuario explícitamente."""
        logger.warning("Bloqueando usuario %s. Razón: %s", self.user_id, reason)
        self._apply_ban()
