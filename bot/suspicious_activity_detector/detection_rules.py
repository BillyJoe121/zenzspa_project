"""
Reglas de detección de contenido/uso sospechoso.
"""
from django.utils import timezone

from ..models import SuspiciousActivity
from .actions import record_activity


def detect_rate_limit_abuse(user, anonymous_user, ip_address):
    """Registra cuando un usuario alcanza el límite de velocidad."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.RATE_LIMIT_HIT,
        severity=SuspiciousActivity.SeverityLevel.MEDIUM,
        description="Usuario alcanzó el límite de velocidad (demasiados mensajes en poco tiempo)",
        context={
            'detection_type': 'velocity_check',
            'timestamp': timezone.now().isoformat()
        }
    )


def detect_daily_limit_abuse(user, anonymous_user, ip_address, current_count, limit):
    """Registra cuando un usuario alcanza el límite diario."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.DAILY_LIMIT_HIT,
        severity=SuspiciousActivity.SeverityLevel.HIGH,
        description=f"Usuario alcanzó el límite diario ({current_count}/{limit} mensajes)",
        context={
            'current_count': current_count,
            'limit': limit,
            'timestamp': timezone.now().isoformat()
        }
    )


def detect_repetitive_messages(user, anonymous_user, ip_address, message):
    """Registra cuando un usuario envía mensajes repetitivos."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.REPETITIVE_MESSAGES,
        severity=SuspiciousActivity.SeverityLevel.HIGH,
        description="Usuario enviando mensajes muy similares repetidamente",
        context={
            'message_sample': message[:200],  # Primeros 200 caracteres
            'timestamp': timezone.now().isoformat()
        }
    )


def detect_jailbreak_attempt(user, anonymous_user, ip_address, message):
    """Registra intento de jailbreak o manipulación del prompt."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.JAILBREAK_ATTEMPT,
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        description="Intento de jailbreak o manipulación del prompt del sistema",
        context={
            'message_sample': message[:200],
            'timestamp': timezone.now().isoformat()
        }
    )


def detect_malicious_content(user, anonymous_user, ip_address, message, conversation_log=None):
    """Registra contenido malicioso detectado por el sistema de seguridad."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.MALICIOUS_CONTENT,
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        description="Contenido malicioso o inapropiado detectado",
        context={
            'message_sample': message[:200],
            'timestamp': timezone.now().isoformat()
        },
        conversation_log=conversation_log
    )


def detect_off_topic_spam(user, anonymous_user, ip_address, message, conversation_log=None):
    """Registra spam o mensajes fuera de tema repetidos."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.OFF_TOPIC_SPAM,
        severity=SuspiciousActivity.SeverityLevel.MEDIUM,
        description="Mensajes fuera de tema o spam detectado",
        context={
            'message_sample': message[:200],
            'timestamp': timezone.now().isoformat()
        },
        conversation_log=conversation_log
    )


def detect_excessive_tokens(user, anonymous_user, ip_address, tokens_used, conversation_log=None):
    """Registra uso excesivo de tokens (mensajes muy largos o complejos)."""
    return record_activity(
        user=user,
        anonymous_user=anonymous_user,
        ip_address=ip_address,
        activity_type=SuspiciousActivity.ActivityType.EXCESSIVE_TOKENS,
        severity=SuspiciousActivity.SeverityLevel.LOW,
        description=f"Uso excesivo de tokens en una conversación ({tokens_used} tokens)",
        context={
            'tokens_used': tokens_used,
            'timestamp': timezone.now().isoformat()
        },
        conversation_log=conversation_log
    )

