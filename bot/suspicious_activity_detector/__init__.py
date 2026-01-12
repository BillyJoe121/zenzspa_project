"""
Facade para detección y análisis de actividad sospechosa.
"""
import logging

from .actions import record_activity
from .analyzer import SuspiciousActivityAnalyzer
from .detection_rules import (
    detect_daily_limit_abuse,
    detect_excessive_tokens,
    detect_jailbreak_attempt,
    detect_malicious_content,
    detect_off_topic_spam,
    detect_rate_limit_abuse,
    detect_repetitive_messages,
)
from .ip_rules import analyze_user_pattern, check_ip_blocked

logger = logging.getLogger(__name__)


class SuspiciousActivityDetector:
    """API principal para detección y registro de actividades sospechosas."""

    check_ip_blocked = staticmethod(check_ip_blocked)
    analyze_user_pattern = staticmethod(analyze_user_pattern)

    @staticmethod
    def record_activity(
        user=None,
        anonymous_user=None,
        ip_address=None,
        activity_type=None,
        severity=None,
        description="",
        context=None,
        conversation_log=None
    ):
        return record_activity(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=activity_type,
            severity=severity,
            description=description,
            context=context,
            conversation_log=conversation_log,
        )

    @classmethod
    def detect_rate_limit_abuse(cls, user, anonymous_user, ip_address):
        return detect_rate_limit_abuse(user, anonymous_user, ip_address)

    @classmethod
    def detect_daily_limit_abuse(cls, user, anonymous_user, ip_address, current_count, limit):
        return detect_daily_limit_abuse(user, anonymous_user, ip_address, current_count, limit)

    @classmethod
    def detect_repetitive_messages(cls, user, anonymous_user, ip_address, message):
        return detect_repetitive_messages(user, anonymous_user, ip_address, message)

    @classmethod
    def detect_jailbreak_attempt(cls, user, anonymous_user, ip_address, message):
        return detect_jailbreak_attempt(user, anonymous_user, ip_address, message)

    @classmethod
    def detect_malicious_content(cls, user, anonymous_user, ip_address, message, conversation_log=None):
        return detect_malicious_content(user, anonymous_user, ip_address, message, conversation_log)

    @classmethod
    def detect_off_topic_spam(cls, user, anonymous_user, ip_address, message, conversation_log=None):
        return detect_off_topic_spam(user, anonymous_user, ip_address, message, conversation_log)

    @classmethod
    def detect_excessive_tokens(cls, user, anonymous_user, ip_address, tokens_used, conversation_log=None):
        return detect_excessive_tokens(user, anonymous_user, ip_address, tokens_used, conversation_log)


__all__ = [
    "SuspiciousActivityDetector",
    "SuspiciousActivityAnalyzer",
]

