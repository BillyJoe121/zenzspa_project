import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from users.models import CustomUser
from ..models import Payment, SubscriptionLog

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
    def fulfill_subscription(payment: Payment, months=1):
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

