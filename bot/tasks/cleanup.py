"""
Tareas de limpieza y mantenimiento relacionadas con el bot.
"""
import logging

from celery import shared_task
from django.utils import timezone

from ..models import BotConversationLog

logger = logging.getLogger(__name__)


@shared_task(name="bot.tasks.cleanup_old_bot_logs")
def cleanup_old_bot_logs(days_to_keep=None):
    """
    BOT-PII-PLAIN: Limpia logs antiguos del bot para mantener la base de datos optimizada
    y cumplir con políticas de retención de datos (GDPR/LGPD).
    
    Args:
        days_to_keep: Número de días de logs a mantener.
                     Si es None, usa BOT_LOG_RETENTION_DAYS de settings (default: 30)
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    from django.conf import settings
    
    # Usar configuración de settings si no se especifica
    if days_to_keep is None:
        days_to_keep = getattr(settings, 'BOT_LOG_RETENTION_DAYS', 30)
    
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
    
    # Contar logs a eliminar
    old_logs = BotConversationLog.objects.filter(created_at__lt=cutoff_date)
    count = old_logs.count()
    
    if count > 0:
        # Eliminar en lotes para evitar bloqueos largos
        old_logs.delete()
        logger.info(
            "🧹 Limpieza de logs del bot: Eliminados %d registros anteriores a %s (retención: %d días)",
            count,
            cutoff_date.strftime('%Y-%m-%d'),
            days_to_keep
        )
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }
    else:
        logger.info("🧹 Limpieza de logs del bot: No hay registros antiguos para eliminar")
        return {
            'deleted_count': 0,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }


@shared_task(name="bot.tasks.cleanup_old_handoffs")
def cleanup_old_handoffs(days_to_keep=None):
    """
    BOT-PII-PLAIN: Limpia solicitudes de handoff resueltas antiguas.
    
    Args:
        days_to_keep: Número de días de handoffs resueltos a mantener.
                     Si es None, usa BOT_HANDOFF_RETENTION_DAYS de settings (default: 90)
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    from django.conf import settings
    from ..models import HumanHandoffRequest
    
    # Usar configuración de settings si no se especifica
    if days_to_keep is None:
        days_to_keep = getattr(settings, 'BOT_HANDOFF_RETENTION_DAYS', 90)
    
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
    
    # Solo eliminar handoffs RESUELTOS antiguos
    old_handoffs = HumanHandoffRequest.objects.filter(
        status=HumanHandoffRequest.Status.RESOLVED,
        resolved_at__lt=cutoff_date
    )
    count = old_handoffs.count()
    
    if count > 0:
        old_handoffs.delete()
        logger.info(
            "🧹 Limpieza de handoffs: Eliminados %d handoffs resueltos anteriores a %s (retención: %d días)",
            count,
            cutoff_date.strftime('%Y-%m-%d'),
            days_to_keep
        )
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }
    else:
        logger.info("🧹 Limpieza de handoffs: No hay handoffs antiguos para eliminar")
        return {
            'deleted_count': 0,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }


@shared_task(name="bot.tasks.cleanup_expired_anonymous_users")
def cleanup_expired_anonymous_users():
    """
    CORRECCIÓN SEGURIDAD: Limpia usuarios anónimos expirados para prevenir
    crecimiento excesivo de la base de datos.

    Esta tarea debe ejecutarse diariamente para eliminar sesiones expiradas
    que no fueron convertidas a usuarios registrados.

    Returns:
        dict: Estadísticas de la limpieza
    """
    from ..models import AnonymousUser

    now = timezone.now()

    # Eliminar usuarios anónimos expirados y no convertidos
    expired_query = AnonymousUser.objects.filter(
        expires_at__lt=now,
        converted_to_user__isnull=True
    )

    count = expired_query.count()

    if count > 0:
        deleted_count, _ = expired_query.delete()
        logger.info(
            "🧹 Limpieza de sesiones anónimas: Eliminados %d usuarios expirados",
            deleted_count
        )
        return {
            'deleted_count': deleted_count,
            'cleanup_date': now.isoformat(),
        }
    return {
        'deleted_count': 0,
        'cleanup_date': now.isoformat(),
    }


@shared_task(name="bot.tasks.check_handoff_timeout")
def check_handoff_timeout(handoff_id):
    """
    Verifica si un handoff ha sido atendido después de 5 minutos.
    Si sigue PENDING, lo marca como EXPIRED y notifica al admin.
    """
    from ..models import HumanHandoffRequest, HumanMessage
    from ..notifications import HandoffNotificationService
    
    try:
        handoff = HumanHandoffRequest.objects.get(id=handoff_id)
    except HumanHandoffRequest.DoesNotExist:
        logger.error("Handoff %s no encontrado para check de timeout", handoff_id)
        return

    # Si ya no está PENDING, ignorar (ya fue atendido o cancelado)
    if handoff.status != HumanHandoffRequest.Status.PENDING:
        return

    # Marcar como EXPIRED
    handoff.status = HumanHandoffRequest.Status.EXPIRED
    handoff.save()

    # Mensaje automático de disculpa
    msg_text = (
        "Lo sentimos, en este momento el personal no se encuentra disponible. "
        "Puedes consultar de nuevo luego, dejarnos tu número para contactarte "
        "o solicitar tu cita y aclarar dudas cuando te acerques a nuestra sede."
    )
    
    HumanMessage.objects.create(
        handoff_request=handoff,
        message=msg_text,
        is_from_staff=True, # Simula ser del staff/sistema
        sender=None # Sistema
    )

    # Notificar al admin
    HandoffNotificationService.send_expired_handoff_notification(handoff)
    
    logger.warning("Handoff %s expiró sin atención. Notificaciones enviadas.", handoff_id)

