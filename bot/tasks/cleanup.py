"""
Tareas de limpieza y mantenimiento relacionadas con el bot.
"""
import logging

from celery import shared_task
from django.utils import timezone

from ..models import BotConversationLog

logger = logging.getLogger(__name__)


@shared_task(name="bot.tasks.cleanup_old_bot_logs")
def cleanup_old_bot_logs(days_to_keep=None, archive_before_delete=True):
    """
    BOT-PII-PLAIN: Limpia logs antiguos del bot para mantener la base de datos optimizada
    y cumplir con políticas de retención de datos (GDPR/LGPD).

    MEJORA: Ahora archiva logs antiguos en JSON antes de eliminarlos para análisis posterior.

    Args:
        days_to_keep: Número de días de logs a mantener.
                     Si es None, usa BOT_LOG_RETENTION_DAYS de settings (default: 30)
        archive_before_delete: Si es True, archiva logs en JSON antes de eliminar (default: True)

    Returns:
        dict: Estadísticas de la limpieza
    """
    from django.conf import settings
    import os
    import json
    from pathlib import Path

    # Usar configuración de settings si no se especifica
    if days_to_keep is None:
        days_to_keep = getattr(settings, 'BOT_LOG_RETENTION_DAYS', 30)

    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)

    # Logs a procesar
    old_logs = BotConversationLog.objects.filter(created_at__lt=cutoff_date)
    count = old_logs.count()

    stats = {
        'processed_count': count,
        'archived_count': 0,
        'deleted_count': 0,
        'cutoff_date': cutoff_date.isoformat(),
        'retention_days': days_to_keep,
        'archive_file': None,
    }

    if count == 0:
        logger.info("🧹 Limpieza de logs del bot: No hay registros antiguos para procesar")
        return stats

    # PASO 1: Archivar si está habilitado
    if archive_before_delete:
        try:
            # Crear directorio de archivo si no existe
            archive_dir = Path(settings.BASE_DIR) / 'logs' / 'bot_archives'
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Nombre del archivo con timestamp
            archive_filename = f"bot_logs_archive_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            archive_path = archive_dir / archive_filename

            # Extraer datos de logs
            logs_data = []
            for log in old_logs.iterator(chunk_size=100):  # Procesar en lotes
                log_entry = {
                    'id': str(log.id),
                    'user_id': str(log.user.id) if log.user else None,
                    'anonymous_user_id': str(log.anonymous_user.id) if log.anonymous_user else None,
                    'message': log.message,
                    'response': log.response,
                    'response_meta': log.response_meta,
                    'was_blocked': log.was_blocked,
                    'block_reason': log.block_reason,
                    'latency_ms': log.latency_ms,
                    'tokens_used': log.tokens_used,
                    'ip_address': log.ip_address,
                    'created_at': log.created_at.isoformat(),
                }
                logs_data.append(log_entry)

            # Guardar en JSON
            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'archive_date': timezone.now().isoformat(),
                    'cutoff_date': cutoff_date.isoformat(),
                    'total_logs': count,
                    'logs': logs_data
                }, f, ensure_ascii=False, indent=2)

            stats['archived_count'] = count
            stats['archive_file'] = str(archive_path)
            logger.info(
                "📦 Archivo creado: %d logs guardados en %s",
                count,
                archive_filename
            )

        except Exception as e:
            logger.error("❌ Error archivando logs: %s", e)
            # Continuar con eliminación aunque falle el archivo

    # PASO 2: Eliminar en lotes para evitar bloqueos largos
    try:
        deleted_count, _ = old_logs.delete()
        stats['deleted_count'] = deleted_count
        logger.info(
            "🧹 Limpieza de logs del bot: Eliminados %d registros anteriores a %s (retención: %d días)",
            deleted_count,
            cutoff_date.strftime('%Y-%m-%d'),
            days_to_keep
        )
    except Exception as e:
        logger.error("❌ Error eliminando logs: %s", e)

    return stats


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
def cleanup_expired_anonymous_users(aggressive=False):
    """
    CORRECCIÓN SEGURIDAD: Limpia usuarios anónimos expirados para prevenir
    crecimiento excesivo de la base de datos.

    Esta tarea debe ejecutarse diariamente para eliminar sesiones expiradas
    que no fueron convertidas a usuarios registrados.

    Args:
        aggressive: Si es True, elimina también sesiones inactivas por más de 7 días
                   aunque no hayan expirado (útil para limpieza profunda)

    Returns:
        dict: Estadísticas de la limpieza
    """
    from ..models import AnonymousUser

    now = timezone.now()
    stats = {
        'expired_deleted': 0,
        'inactive_deleted': 0,
        'total_deleted': 0,
        'cleanup_date': now.isoformat(),
    }

    # 1. Eliminar usuarios anónimos expirados y no convertidos
    expired_query = AnonymousUser.objects.filter(
        expires_at__lt=now,
        converted_to_user__isnull=True
    )

    expired_count = expired_query.count()

    if expired_count > 0:
        deleted_count, _ = expired_query.delete()
        stats['expired_deleted'] = deleted_count
        logger.info(
            "🧹 Limpieza de sesiones anónimas: Eliminados %d usuarios expirados",
            deleted_count
        )

    # 2. Limpieza agresiva: sesiones inactivas por más de 7 días (sin conversión)
    if aggressive:
        inactive_threshold = now - timezone.timedelta(days=7)
        inactive_query = AnonymousUser.objects.filter(
            last_activity__lt=inactive_threshold,
            converted_to_user__isnull=True
        )

        inactive_count = inactive_query.count()

        if inactive_count > 0:
            deleted_count, _ = inactive_query.delete()
            stats['inactive_deleted'] = deleted_count
            logger.info(
                "🧹 Limpieza agresiva de sesiones anónimas: Eliminados %d usuarios inactivos por más de 7 días",
                deleted_count
            )

    # 3. Limpieza de usuarios anónimos sin ninguna conversación (zombies)
    # Estos son usuarios que se crearon pero nunca interactuaron
    zombie_threshold = now - timezone.timedelta(hours=24)
    zombie_query = AnonymousUser.objects.filter(
        created_at__lt=zombie_threshold,
        converted_to_user__isnull=True,
        bot_conversations__isnull=True  # Sin ninguna conversación
    )

    zombie_count = zombie_query.count()
    if zombie_count > 0:
        deleted_count, _ = zombie_query.delete()
        stats['zombie_deleted'] = zombie_count
        logger.info(
            "🧹 Limpieza de sesiones zombie: Eliminados %d usuarios anónimos sin actividad",
            deleted_count
        )

    stats['total_deleted'] = (
        stats['expired_deleted'] +
        stats.get('inactive_deleted', 0) +
        stats.get('zombie_deleted', 0)
    )

    if stats['total_deleted'] > 0:
        logger.info(
            "✅ Limpieza completada: %d usuarios anónimos eliminados (expired: %d, inactive: %d, zombie: %d)",
            stats['total_deleted'],
            stats['expired_deleted'],
            stats.get('inactive_deleted', 0),
            stats.get('zombie_deleted', 0)
        )

    return stats


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

