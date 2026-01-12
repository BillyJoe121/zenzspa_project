from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver, Signal
from django.contrib.auth import get_user_model
from django.utils import timezone
from spa.models import StaffAvailability
import datetime
import logging
from core.models import AuditLog
from core.utils import safe_audit_log

from .models import UserSession

CustomUser = get_user_model()
user_session_logged_in = Signal()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=UserSession)
def log_user_session_changes(sender, instance, created, **kwargs):
    """Log de cambios en UserSession para debugging."""
    import traceback
    if created:
        logger.info(
            "[SESSION_CREATED] Nueva sesión para %s - ID: %s, JTI: %s, IP: %s",
            instance.user.phone_number,
            instance.id,
            instance.refresh_token_jti,
            instance.ip_address
        )
    else:
        # Detectar si se marcó como inactiva
        if not instance.is_active:
            stack = ''.join(traceback.format_stack()[:-1])
            logger.warning(
                "[SESSION_DEACTIVATED] Sesión %s marcada como inactiva para %s. JTI: %s. Llamado desde:\n%s",
                instance.id,
                instance.user.phone_number,
                instance.refresh_token_jti,
                stack
            )


@receiver(post_save, sender=CustomUser)
def create_default_staff_availability(sender, instance, created, **kwargs):
    """
    Señal que se activa después de guardar un CustomUser.
    Si el usuario es nuevo y es STAFF, se crea su horario por defecto.
    """
    if created and instance.role == CustomUser.Role.STAFF:
        # Horarios por defecto
        morning_start = datetime.time(8, 0)
        morning_end = datetime.time(13, 0)
        afternoon_start = datetime.time(14, 0)
        afternoon_end = datetime.time(19, 0)

        # CORRECCIÓN: Iterar de Lunes (1) a Sábado (6).
        # El rango correcto es range(1, 7) para generar los números del 1 al 6.
        for day in range(1, 7):
            StaffAvailability.objects.create(
                staff_member=instance,
                day_of_week=day,
                start_time=morning_start,
                end_time=morning_end
            )
            StaffAvailability.objects.create(
                staff_member=instance,
                day_of_week=day,
                start_time=afternoon_start,
                end_time=afternoon_end
            )
        print(
            f"Horario por defecto creado para el nuevo miembro del staff: {instance.phone_number}")


@receiver(user_session_logged_in)
def handle_user_session(sender, user, refresh_token_jti, ip_address, user_agent, **kwargs):
    """
    Registra o actualiza la sesión del usuario cuando se emite un token.
    """
    session, created = UserSession.objects.get_or_create(
        user=user,
        refresh_token_jti=refresh_token_jti,
        defaults={
            'ip_address': ip_address,
            'user_agent': user_agent,
            'is_active': True,
        },
    )
    if not created:
        session.ip_address = ip_address
        session.user_agent = user_agent
        session.is_active = True
    session.last_activity = timezone.now()
    session.save(update_fields=['ip_address', 'user_agent', 'is_active', 'last_activity', 'updated_at'])


@receiver(post_save, sender=CustomUser)
def audit_role_change(sender, instance, created, **kwargs):
    if created:
        return

    # Detectar qué campos cambiaron para logging
    import traceback
    changed_fields = []
    if hasattr(instance, '_old_role'):
        if instance._old_role != instance.role:
            changed_fields.append(f"role: {instance._old_role} -> {instance.role}")

    # Log de todos los saves de usuario para debugging
    if changed_fields:
        stack = ''.join(traceback.format_stack()[:-1])
        logger.info(
            "[USER_SAVE] Usuario %s modificado. Campos cambiados: %s. Llamado desde:\n%s",
            instance.phone_number,
            ', '.join(changed_fields),
            stack
        )

    old_role = getattr(instance, "_old_role", None)
    if old_role and old_role != instance.role:
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=instance,
            details={"from": old_role, "to": instance.role},
        )


@receiver(pre_save, sender=CustomUser)
def stash_old_role(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
        instance._old_role = previous.role
    except sender.DoesNotExist:
        instance._old_role = None
