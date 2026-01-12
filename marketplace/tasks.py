import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from notifications.services import NotificationService

logger = logging.getLogger(__name__)


@shared_task
def notify_order_status_change(order_id, new_status):
    from .models import Order
    from .services.notification_service import MarketplaceNotificationService

    try:
        order = Order.objects.select_related('user').get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("Orden %s no encontrada para notificación.", order_id)
        return "missing"

    event_map = {
        Order.OrderStatus.CANCELLED: "ORDER_CANCELLED",
    }
    ready_status = getattr(Order.OrderStatus, "READY_FOR_PICKUP", None)
    if ready_status:
        event_map[ready_status] = "ORDER_READY_FOR_PICKUP"
    specialized_event, specialized_context = MarketplaceNotificationService.get_event_payload(order, new_status)

    event_code = specialized_event or event_map.get(new_status)
    if not event_code:
        return "no_event"

    if specialized_context:
        context = specialized_context
    else:
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


@shared_task
def cleanup_expired_carts():
    """
    Desactiva y limpia carritos vencidos para liberar el constraint de carrito activo.
    """
    from .models import Cart

    now = timezone.now()
    count = 0
    with transaction.atomic():
        expired = (
            Cart.objects.select_for_update()
            .filter(is_active=True, expires_at__isnull=False, expires_at__lt=now)
        )
        for cart in expired:
            cart.items.all().delete()
            cart.is_active = False
            cart.save(update_fields=['is_active', 'updated_at'])
            count += 1
    return f"Carritos expirados limpiados: {count}"
