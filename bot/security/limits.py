import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


class StrikeLimitMixin:
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


class DailyLimitMixin:
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


class BanMixin:
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

    def block_user(self, reason: str = "Bloqueo manual"):
        """Bloquea al usuario explícitamente."""
        logger.warning("Bloqueando usuario %s. Razón: %s", self.user_id, reason)
        self._apply_ban()
