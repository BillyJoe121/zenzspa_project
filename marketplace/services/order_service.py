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

        if new_status in [Order.OrderStatus.CANCELLED, Order.OrderStatus.REFUNDED]:
            try:
                from finances.cashback_service import CashbackService
                CashbackService.revert_cashback(order)
            except Exception as e:
                logger.error("Error reverting cashback for order %s: %s", order.id, e)


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
                InventoryMovement.objects.get_or_create(
                    variant=variant,
                    reference_order=order,
                    movement_type=movement_type,
                    defaults={
                        "quantity": release_qty,
                        "description": reason,
                        "created_by": changed_by,
                    },
                )
        order.reservation_expires_at = None
        order.save(update_fields=['reservation_expires_at', 'updated_at'])
        return order

    @classmethod
    @transaction.atomic
    def confirm_payment(cls, order, paid_amount=None):
        """
        Confirma el pago de una orden.

        Soporta pagos mixtos (créditos + pasarela) sumando todos los pagos exitosos
        asociados a la orden (APPROVED + PAID_WITH_CREDIT).

        Args:
            order: Orden a confirmar
            paid_amount: Monto pagado según gateway (opcional, solo para compatibilidad)
        """
        if order.status == Order.OrderStatus.PAID:
            raise BusinessLogicError(detail="La orden ya ha sido pagada.")

        if order.status == Order.OrderStatus.CANCELLED:
            raise BusinessLogicError(detail="La orden está cancelada y no se puede pagar.")

        cls._validate_pricing(order)

        # Calcular el total pagado sumando TODOS los pagos exitosos de la orden
        from finances.models import Payment
        from django.db.models import Sum, Q

        total_paid = order.payments.filter(
            Q(status=Payment.PaymentStatus.APPROVED) | Q(status=Payment.PaymentStatus.PAID_WITH_CREDIT)
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Validar que la suma de pagos cubra el total de la orden
        if abs(total_paid - order.total_amount) > Decimal('0.01'):
            raise BusinessLogicError(
                detail=f"El total pagado ({total_paid}) no coincide con el total de la orden ({order.total_amount}).",
                internal_code="MKT-AMOUNT-MISMATCH",
                extra={
                    "total_paid": str(total_paid),
                    "order_total": str(order.total_amount),
                    "payments_count": order.payments.filter(
                        status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT]
                    ).count()
                }
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

        # Vaciar el carrito del usuario ahora que el pago fue exitoso
        try:
            from ..models import Cart
            # Buscar el carrito activo del usuario
            cart = Cart.objects.filter(user=order.user, is_active=True).first()
            if cart:
                deleted_count = cart.items.all().delete()[0]
                logger.info(
                    "Carrito vaciado después de pago exitoso: user=%s, order=%s, items_deleted=%d",
                    order.user.id, order.id, deleted_count
                )
            else:
                logger.warning(
                    "No se encontró carrito activo para vaciar: user=%s, order=%s",
                    order.user.id, order.id
                )
        except Exception as e:
            # Si falla, loguear el error pero no bloquear el pago
            logger.error(
                "Error al vaciar carrito después de pago: user=%s, order=%s, error=%s",
                order.user.id, order.id, str(e)
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
        
        # Sumar costo de envío si existe
        if order.shipping_cost:
            recalculated += order.shipping_cost

        if recalculated != order.total_amount:
            raise BusinessLogicError(
                detail=f"El precio de la orden ({order.total_amount}) no coincide con el cálculo actual ({recalculated}).",
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
            InventoryMovement.objects.get_or_create(
                variant=variant,
                reference_order=order,
                movement_type=InventoryMovement.MovementType.SALE,
                defaults={
                    "quantity": item.quantity,
                    "description": "Venta confirmada",
                    "created_by": None,
                },
            )
            InventoryService.check_low_stock(variant)
