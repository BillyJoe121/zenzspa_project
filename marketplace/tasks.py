import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from notifications.services import NotificationService

logger = logging.getLogger(__name__)


@shared_task
def notify_order_status_change(order_id, new_status):
    from .models import Order

    try:
        order = Order.objects.select_related('user').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("Orden %s no encontrada para notificación.", order_id)
        return "missing"

    event_map = {
        Order.OrderStatus.SHIPPED: "ORDER_SHIPPED",
        Order.OrderStatus.DELIVERED: "ORDER_DELIVERED",
        Order.OrderStatus.CANCELLED: "ORDER_CANCELLED",
    }
    ready_status = getattr(Order.OrderStatus, "READY_FOR_PICKUP", None)
    if ready_status:
        event_map[ready_status] = "ORDER_READY_FOR_PICKUP"
    event_code = event_map.get(new_status)
    if not event_code:
        return "no_event"

    context = {
        "order_id": str(order.id),
        "tracking_number": order.tracking_number,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "status": new_status,
    }
    try:
        NotificationService.send_notification(
            user=order.user,
            event_code=event_code,
            context=context,
        )
    except Exception:
        logger.exception("No se pudo enviar notificación %s para la orden %s", event_code, order.id)
    return "ok"


@shared_task
def release_expired_order_reservations():
    from .models import Order
    from .services import OrderService

    now = timezone.now()
    with transaction.atomic():
        expired_orders = (
            Order.objects.select_for_update()
            .filter(
                status=Order.OrderStatus.PENDING_PAYMENT,
                reservation_expires_at__isnull=False,
                reservation_expires_at__lt=now,
            )
        )
        count = 0
        for order in expired_orders:
            OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
            count += 1
    return f"Reservas liberadas: {count}"
