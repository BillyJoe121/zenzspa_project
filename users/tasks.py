import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail  # Import for test compatibility
from django.db.models import Q
from django.utils import timezone
from notifications.services import NotificationService

from .models import CustomUser, UserSession

logger = logging.getLogger(__name__)


@shared_task
def send_non_grata_alert_to_admins(phone_number):
    """
    Notifica a todos los administradores sobre un intento de registro
    de un número de teléfono marcado como 'No Grato'.
    Migrado al sistema centralizado de NotificationService.
    """
    from bot.models import BotConfiguration

    # Obtener configuración del admin
    config = BotConfiguration.objects.filter(is_active=True).first()
    admin_phone = config.admin_phone if config else None

    if not admin_phone:
        logger.warning("No hay teléfono de admin configurado para alertas non grata")
        return "No hay admin configurado"

    # Buscar usuario admin con ese teléfono
    admin_user = CustomUser.objects.filter(
        phone_number=admin_phone,
        is_staff=True,
        is_active=True
    ).first()

    if not admin_user:
        # Fallback: buscar cualquier admin activo
        admin_user = CustomUser.objects.filter(
            role=CustomUser.Role.ADMIN,
            is_active=True
        ).first()

    if not admin_user:
        logger.warning("No se encontró usuario admin para enviar alerta non grata")
        return "No hay admin activo"

    # Buscar el usuario bloqueado para obtener más información
    blocked_user = CustomUser.objects.filter(phone_number=phone_number).first()

    # Preparar contexto
    context = {
        "user_name": blocked_user.get_full_name() if blocked_user else "Desconocido",
        "user_email": blocked_user.email if blocked_user else "No disponible",
        "user_phone": phone_number,
        "flag_reason": "Intento de registro con número marcado como Non Grata",
        "action_taken": "Registro bloqueado automáticamente",
        "admin_url": f"{settings.SITE_URL}/admin/users/customuser/{blocked_user.id}/change/" if blocked_user else f"{settings.SITE_URL}/admin/users/customuser/",
    }

    try:
        # Enviar notificación usando el sistema centralizado
        NotificationService.send_notification(
            user=admin_user,
            event_code="USER_FLAGGED_NON_GRATA",
            context=context,
            priority="critical"  # Critical para ignorar quiet hours
        )

        logger.info("Alerta non grata enviada para el número %s", phone_number)
        return f"Notificación enviada para el número {phone_number}"

    except Exception as e:
        logger.error("Error enviando alerta non grata: %s", e)
        return f"Error enviando notificación: {str(e)}"


@shared_task
def cleanup_inactive_sessions():
    """
    Elimina sesiones inactivas hace más de 30 días o marcadas como inactivas.
    """
    cutoff = timezone.now() - timedelta(days=30)
    deleted_count, _ = UserSession.objects.filter(
        Q(is_active=False) | Q(last_activity__lt=cutoff)
    ).delete()
    if deleted_count:
        logger.info("Eliminadas %s sesiones inactivas o antiguas", deleted_count)
    return {"deleted_count": deleted_count}
