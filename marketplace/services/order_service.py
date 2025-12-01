"""
Servicio para gestión de transiciones de estado de órdenes.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from ..models import InventoryMovement, Order
from ..tasks import notify_order_status_change
from .inventory_service import InventoryService
from .notification_service import MarketplaceNotificationService

logger = logging.getLogger(__name__)


class OrderService:
    """
    Maneja transiciones de estado para órdenes con validaciones.
    """

    ALLOWED_TRANSITIONS = {
        Order.OrderStatus.PENDING_PAYMENT: {Order.OrderStatus.PAID, Order.OrderStatus.CANCELLED, Order.OrderStatus.FRAUD_ALERT},
        Order.OrderStatus.PAID: {Order.OrderStatus.PREPARING, Order.OrderStatus.CANCELLED, Order.OrderStatus.RETURN_REQUESTED},
        Order.OrderStatus.PREPARING: {Order.OrderStatus.SHIPPED, Order.OrderStatus.CANCELLED},
        Order.OrderStatus.SHIPPED: {Order.OrderStatus.DELIVERED, Order.OrderStatus.RETURN_REQUESTED},
        Order.OrderStatus.DELIVERED: {Order.OrderStatus.RETURN_REQUESTED},
        Order.OrderStatus.RETURN_REQUESTED: {Order.OrderStatus.RETURN_APPROVED, Order.OrderStatus.RETURN_REJECTED},
        Order.OrderStatus.RETURN_APPROVED: {Order.OrderStatus.REFUNDED},
    }

    STATE_NOTIFICATION_EVENTS = {
        Order.OrderStatus.CANCELLED: "ORDER_CANCELLED",
    }
    READY_FOR_PICKUP_STATUS = getattr(Order.OrderStatus, "READY_FOR_PICKUP", None)
    if READY_FOR_PICKUP_STATUS:
        STATE_NOTIFICATION_EVENTS[READY_FOR_PICKUP_STATUS] = "ORDER_READY_FOR_PICKUP"

    @classmethod
    @transaction.atomic
    def transition_to(cls, order, new_status, changed_by=None):
        current = order.status
        if current == new_status:
            return order
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            logger.warning(
                "Intento de transición inválida: order_id=%s, from=%s, to=%s, user=%s",
                order.id, current, new_status, changed_by.id if changed_by else None
            )
            raise BusinessLogicError(
                detail=f"No se puede cambiar el estado de {current} a {new_status}.",
                internal_code="MKT-STATE",
                extra={"current_status": current, "attempted_status": new_status}
            )

        order.status = new_status
        if new_status == Order.OrderStatus.DELIVERED:
            order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at', 'updated_at'])

        logger.info(
            "Transición de estado: order_id=%s, from=%s, to=%s, changed_by=%s",
            order.id, current, new_status, changed_by.id if changed_by else None
        )

        if (
            new_status == Order.OrderStatus.CANCELLED
            and current == Order.OrderStatus.PENDING_PAYMENT
        ):
            cls.release_reservation(
                order,
                movement_type=InventoryMovement.MovementType.RESERVATION_RELEASE,
                reason="Reserva liberada por cancelación.",
                changed_by=changed_by,
            )

        cls._dispatch_notifications(order, new_status)
        return order

    @classmethod
    def _dispatch_notifications(cls, order, new_status):
        if new_status in cls.STATE_NOTIFICATION_EVENTS:
            try:
                notify_order_status_change.delay(str(order.id), new_status)
            except Exception:
                logger.exception("No se pudo notificar el cambio de estado de la orden %s", order.id)
        cls._send_status_whatsapp(order, new_status)

    @classmethod
    def _send_status_whatsapp(cls, order, new_status):
        MarketplaceNotificationService.send_order_status_update(order, new_status)



    @classmethod
    def _is_ready_for_pickup_state(cls, order, new_status):
        if cls.READY_FOR_PICKUP_STATUS:
            return new_status == cls.READY_FOR_PICKUP_STATUS
        return (
            new_status == Order.OrderStatus.PREPARING
            and order.delivery_option == Order.DeliveryOptions.PICKUP
        )

    @staticmethod
    def _format_customer_name(order):
        user = order.user
        return (
            getattr(user, "first_name", "")
            or getattr(user, "last_name", "")
            or getattr(user, "email", "")
            or "cliente"
        )

    @classmethod
    @transaction.atomic
    def release_reservation(cls, order, movement_type=InventoryMovement.MovementType.RESERVATION_RELEASE, reason="Reserva liberada", changed_by=None):
        for item in order.items.select_related('variant').select_for_update():
            variant = item.variant
            release_qty = min(item.quantity, variant.reserved_stock)
            if release_qty > 0:
                variant.reserved_stock -= release_qty
                variant.save(update_fields=['reserved_stock'])
                InventoryMovement.objects.create(
                    variant=variant,
                    quantity=release_qty,
                    movement_type=movement_type,
                    reference_order=order,
                    description=reason,
                    created_by=changed_by,
                )
        order.reservation_expires_at = None
        order.save(update_fields=['reservation_expires_at', 'updated_at'])
        return order

    @classmethod
    @transaction.atomic
    def confirm_payment(cls, order, paid_amount=None):
        """
        Confirma el pago de una orden.

        Args:
            order: Orden a confirmar
            paid_amount: Monto pagado según gateway (opcional pero recomendado)
        """
        if order.status == Order.OrderStatus.PAID:
            raise BusinessLogicError(detail="La orden ya ha sido pagada.")

        if order.status == Order.OrderStatus.CANCELLED:
            raise BusinessLogicError(detail="La orden está cancelada y no se puede pagar.")

        cls._validate_pricing(order)

        # Validar monto pagado si se proporciona
        if paid_amount is not None:
            # Convertir a Decimal si es necesario
            if not isinstance(paid_amount, Decimal):
                paid_amount = Decimal(str(paid_amount))

            if abs(paid_amount - order.total_amount) > Decimal('0.01'):
                raise BusinessLogicError(
                    detail=f"El monto pagado ({paid_amount}) no coincide con el total de la orden ({order.total_amount}).",
                    internal_code="MKT-AMOUNT-MISMATCH"
                )

        # Reforzar atomicidad y lock sobre la orden
        order = Order.objects.select_for_update().get(pk=order.pk)

        cls._capture_stock(order)
        order.reservation_expires_at = None
        order.status = Order.OrderStatus.PAID
        order.save(update_fields=['reservation_expires_at', 'status', 'updated_at'])

        logger.info(
            "Pago confirmado: order_id=%s, user=%s, total=%s",
            order.id, order.user.id, order.total_amount
        )
        return order

    @classmethod
    def _validate_pricing(cls, order):
        recalculated = Decimal('0')
        for item in order.items.select_related('variant__product'):
            variant = item.variant
            current_price = variant.price
            if order.user.is_vip and variant.vip_price:
                current_price = variant.vip_price
            recalculated += current_price * item.quantity
        if recalculated != order.total_amount:
            raise BusinessLogicError(
                detail="El precio de la orden no coincide con el de los productos actuales.",
                internal_code="MKT-PRICE",
            )

    @classmethod
    def _capture_stock(cls, order):
        for item in order.items.select_related('variant').select_for_update():
            variant = item.variant
            if variant.stock < item.quantity:
                raise BusinessLogicError(
                    detail=f"Stock insuficiente para confirmar el pago del ítem {variant}.",
                    internal_code="MKT-STOCK",
                )
            if variant.reserved_stock >= item.quantity:
                variant.reserved_stock -= item.quantity
            else:
                shortfall = item.quantity - variant.reserved_stock
                available = variant.stock - variant.reserved_stock
                if available < shortfall:
                    raise BusinessLogicError(
                        detail=f"La reserva expiró y no hay stock suficiente para {variant}.",
                        internal_code="MKT-STOCK-EXPIRED",
                    )
                variant.reserved_stock = 0
            variant.stock -= item.quantity
            variant.save(update_fields=['stock', 'reserved_stock'])
            InventoryMovement.objects.create(
                variant=variant,
                quantity=item.quantity,
                movement_type=InventoryMovement.MovementType.SALE,
                reference_order=order,
                description="Venta confirmada",
                created_by=None,
            )
            InventoryService.check_low_stock(variant)
