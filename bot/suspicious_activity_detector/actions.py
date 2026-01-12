"""
Acciones base para registrar actividad sospechosa.
"""
import logging

from ..models import SuspiciousActivity

logger = logging.getLogger(__name__)


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
    """
    Registra una actividad sospechosa en la base de datos.
    Si es crítica, envía alerta por email y verifica auto-bloqueo.
    """
    try:
        activity = SuspiciousActivity.objects.create(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            activity_type=activity_type,
            severity=severity,
            description=description,
            context=context or {},
            conversation_log=conversation_log
        )

        logger.warning(
            "Actividad sospechosa registrada: %s - %s - IP: %s - Severidad: %s",
            activity.participant_identifier,
            activity.get_activity_type_display(),
            ip_address,
            activity.get_severity_display()
        )

        # Si es CRÍTICA, enviar alerta y verificar auto-bloqueo
        if severity == SuspiciousActivity.SeverityLevel.CRITICAL:
            # Importar aquí para evitar circular imports
            from ..alerts import SuspiciousActivityAlertService, AutoBlockService

            # Enviar alerta por email
            SuspiciousActivityAlertService.send_critical_activity_alert(activity)

            # Verificar si debe bloquearse automáticamente
            was_blocked, block = AutoBlockService.check_and_auto_block(
                user=user,
                anonymous_user=anonymous_user,
                ip_address=ip_address
            )

            if was_blocked:
                logger.critical(
                    "IP %s auto-bloqueada después de actividad crítica",
                    ip_address
                )

        return activity

    except Exception as e:
        logger.error("Error registrando actividad sospechosa: %s", e)
        return None

