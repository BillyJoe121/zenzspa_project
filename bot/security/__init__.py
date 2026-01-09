from django.core.cache import cache

from .limits import BanMixin, DailyLimitMixin, StrikeLimitMixin
from .locking import LockingMixin
from .rate_limits import RateLimitMixin
from .sanitization import anonymize_pii, sanitize_for_logging
from .validation import InputValidationMixin


class BotSecurityService(
    LockingMixin,
    InputValidationMixin,
    RateLimitMixin,
    StrikeLimitMixin,
    DailyLimitMixin,
    BanMixin,
):
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

