"""
Utilidades compartidas para las vistas de usuarios.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from ..models import OTPAttempt, UserSession
from ..utils import get_client_ip

logger = logging.getLogger(__name__)

# Constantes de configuración
OTP_PHONE_RECAPTCHA_THRESHOLD = getattr(settings, "OTP_PHONE_RECAPTCHA_THRESHOLD", 3)
OTP_IP_RECAPTCHA_THRESHOLD = getattr(settings, "OTP_IP_RECAPTCHA_THRESHOLD", 5)
RECAPTCHA_ACTION_OTP_REQUEST = "auth__otp_request"
RECAPTCHA_ACTION_OTP_VERIFY = "auth__otp_verify"
RECAPTCHA_ACTION_PASSWORD_RESET_REQUEST = "auth__password_reset_request"


def log_otp_attempt(phone_number, attempt_type, success, request, metadata=None):
    """Registra un intento de OTP en la base de datos."""
    OTPAttempt.objects.create(
        phone_number=phone_number,
        attempt_type=attempt_type,
        is_successful=success,
        ip_address=get_client_ip(request),
        metadata=metadata or {},
    )


def requires_recaptcha(phone_number, ip_address, attempt_type):
    """Verifica si se requiere reCAPTCHA basado en intentos previos."""
    since = timezone.now() - timedelta(hours=1)
    phone_attempts = OTPAttempt.objects.filter(
        phone_number=phone_number,
        attempt_type=attempt_type,
        created_at__gte=since,
    ).count()
    ip_attempts = OTPAttempt.objects.filter(
        ip_address=ip_address,
        attempt_type=attempt_type,
        created_at__gte=since,
    ).count()
    return phone_attempts >= OTP_PHONE_RECAPTCHA_THRESHOLD or ip_attempts >= OTP_IP_RECAPTCHA_THRESHOLD


def deactivate_session_for_jti(user, jti):
    """Desactiva una sesión específica por su JTI."""
    UserSession.objects.filter(
        user=user,
        refresh_token_jti=jti,
        is_active=True
    ).update(is_active=False, updated_at=timezone.now())


def revoke_all_sessions(user):
    """
    MEJORA #20: Revoca todas las sesiones activas del usuario.
    Invalida tokens JWT y sesiones en UserSession para forzar re-autenticación.
    """
    import traceback
    import sys

    # Log del stack trace para ver quién llamó esta función
    stack = ''.join(traceback.format_stack()[:-1])
    logger.warning(
        "[REVOKE_ALL_SESSIONS] Revocando todas las sesiones para %s. Llamado desde:\n%s",
        user.phone_number,
        stack
    )

    # Invalidar todos los tokens JWT
    tokens = OutstandingToken.objects.filter(user=user)
    blacklisted_count = 0
    for token in tokens:
        try:
            BlacklistedToken.objects.get_or_create(token=token)
            blacklisted_count += 1
        except Exception as e:
            logger.error(
                "[REVOKE_ALL_SESSIONS] Error al blacklist token para %s: %s",
                user.phone_number,
                str(e)
            )
            continue

    # Invalidar todas las sesiones activas
    active_sessions_before = list(UserSession.objects.filter(user=user, is_active=True).values('id', 'refresh_token_jti', 'ip_address', 'created_at'))
    invalidated_sessions = UserSession.objects.filter(
        user=user, is_active=True
    ).update(is_active=False, updated_at=timezone.now())

    logger.warning(
        "[REVOKE_ALL_SESSIONS] Usuario %s: %d tokens blacklisted, %d sesiones invalidadas. Sesiones afectadas: %s",
        user.phone_number,
        blacklisted_count,
        invalidated_sessions,
        active_sessions_before
    )
