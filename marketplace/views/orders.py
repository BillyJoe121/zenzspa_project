from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets

from users.models import CustomUser

from ..models import Order
from ..serializers import OrderSerializer
from .orders_actions import OrderActionsMixin


class OrderViewSet(OrderActionsMixin, viewsets.ModelViewSet):
    """
    ViewSet para que un usuario pueda ver su historial de órdenes.
    Los clientes pueden eliminar órdenes en estado PENDING_PAYMENT.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    STAFF_VISIBLE_STATUSES = {
        Order.OrderStatus.PENDING_PAYMENT,
        Order.OrderStatus.PAID,
        Order.OrderStatus.PREPARING,
        Order.OrderStatus.SHIPPED,
        Order.OrderStatus.RETURN_REQUESTED,
        Order.OrderStatus.RETURN_APPROVED,
        Order.OrderStatus.RETURN_REJECTED,
        Order.OrderStatus.FRAUD_ALERT,
    }
    STAFF_LOOKBACK_DAYS = 30

    def get_queryset(self):
        """Asegura que cada usuario solo pueda ver sus propias órdenes."""
        queryset = Order.objects.prefetch_related('items__variant__product')
        user = self.request.user
        if getattr(user, 'role', None) == CustomUser.Role.ADMIN:
            return queryset
        if getattr(user, 'role', None) == CustomUser.Role.STAFF:
            recent_threshold = timezone.now() - timedelta(days=self.STAFF_LOOKBACK_DAYS)
            return queryset.filter(
                Q(status__in=self.STAFF_VISIBLE_STATUSES)
                | Q(created_at__gte=recent_threshold)
            )
        return queryset.filter(user=user)
