"""
Servicios de gestión de suscripciones VIP.

Migrado desde spa.services.vip para centralizar toda la lógica
de pagos y suscripciones en el módulo finances.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from users.models import CustomUser

logger = logging.getLogger(__name__)


class VipMembershipService:
    """
    Funciones auxiliares para manejar la extensión de membresías VIP.
    """

    @staticmethod
    @transaction.atomic
    def extend_membership(user, months):
        if not user:
            return None, None
        months = int(months or 0)
        if months <= 0:
            return None, None
        today = timezone.now().date()
        start_date = today
        if user.is_vip and user.vip_expires_at and user.vip_expires_at >= today:
            start_date = user.vip_expires_at + timedelta(days=1)
        end_date = start_date + timedelta(days=30 * months)
        user.role = CustomUser.Role.VIP
        update_fields = ['role', 'vip_expires_at', 'updated_at']
        user.vip_expires_at = end_date
        if not user.vip_active_since:
            user.vip_active_since = start_date
            update_fields.append('vip_active_since')
        user.save(update_fields=update_fields)
        return start_date, end_date


class VipSubscriptionService:
    """
    Servicio para manejar la lógica de negocio de las suscripciones VIP.
    """
    @staticmethod
    @transaction.atomic
    def fulfill_subscription(payment, months=1):
        """
        Procesa el fulfillment de una suscripción VIP después de un pago exitoso.

        Args:
            payment: Instancia de finances.models.Payment
            months: Número de meses a extender la membresía
        """
        # Import local para evitar ciclos durante la transición
        from .models import SubscriptionLog

        user = payment.user
        start_date, end_date = VipMembershipService.extend_membership(
            user, months)
        if not start_date:
            return
        user.vip_auto_renew = True
        user.vip_failed_payments = 0
        user.save(update_fields=['vip_auto_renew', 'vip_expires_at', 'role',
                  'vip_active_since', 'vip_failed_payments', 'updated_at'])
        SubscriptionLog.objects.create(
            user=user,
            payment=payment,
            start_date=start_date,
            end_date=end_date
        )

        # Enviar notificación de bienvenida VIP solo si es primera suscripción
        # (no renovaciones, ya que start_date sería en el futuro para renovaciones)
        if start_date == timezone.now().date():
            try:
                from notifications.services import NotificationService
                from core.models import GlobalSettings
                settings_obj = GlobalSettings.load()
                
                # Construir resumen de beneficios
                benefits = []
                if settings_obj.vip_discount_percentage > 0:
                    benefits.append(f"{settings_obj.vip_discount_percentage}% de descuento en servicios")
                if settings_obj.cashback_percentage > 0:
                    benefits.append(f"{settings_obj.cashback_percentage}% de cashback")
                benefits_summary = ", ".join(benefits) if benefits else "beneficios exclusivos"
                
                NotificationService.send_notification(
                    user=user,
                    event_code="VIP_WELCOME",
                    context={
                        "user_name": user.get_full_name() or user.first_name or "Cliente",
                        "benefits_summary": benefits_summary,
                    },
                    priority="high"
                )
            except Exception:
                logger.exception("Error enviando notificación de bienvenida VIP para usuario %s", user.id)
