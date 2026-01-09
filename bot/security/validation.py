import logging
import re

from .sanitization import sanitize_for_logging

logger = logging.getLogger(__name__)


class InputValidationMixin:
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
