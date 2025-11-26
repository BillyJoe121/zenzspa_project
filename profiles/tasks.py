from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_kiosk_sessions():
    """
    Elimina sesiones de kiosk completadas hace más de 7 días.
    También limpia sesiones bloqueadas hace más de 30 días.
    Esta tarea debe ejecutarse diariamente.
    """
    from .models import KioskSession
    
    # Limpiar sesiones completadas antiguas
    cutoff_completed = timezone.now() - timedelta(days=7)
    deleted_completed, _ = KioskSession.objects.filter(
        status=KioskSession.Status.COMPLETED,
        updated_at__lt=cutoff_completed
    ).delete()
    
    # Limpiar sesiones bloqueadas muy antiguas
    cutoff_locked = timezone.now() - timedelta(days=30)
    deleted_locked, _ = KioskSession.objects.filter(
        status=KioskSession.Status.LOCKED,
        updated_at__lt=cutoff_locked
    ).delete()
    
    result = {
        "deleted_completed": deleted_completed,
        "deleted_locked": deleted_locked,
        "total_deleted": deleted_completed + deleted_locked
    }
    
    logger.info(
        "Limpieza de sesiones de kiosk: %d completadas, %d bloqueadas, %d total",
        deleted_completed,
        deleted_locked,
        result['total_deleted']
    )
    
    return result
