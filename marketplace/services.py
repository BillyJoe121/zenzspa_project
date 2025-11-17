import logging
import uuid
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from core.models import GlobalSettings
from spa.models import ClientCredit
from .models import Order, OrderItem, ProductVariant, InventoryMovement
from marketplace.tasks import notify_order_status_change

logger = logging.getLogger(__name__)

class OrderCreationService:
    """
    Servicio para encapsular la lógica de creación de una orden a partir de un carrito.
    """
    def __init__(self, user, cart, data):
        self.user = user
        self.cart = cart
        self.data = data # Datos del request (ej. delivery_option)

    @transaction.atomic
    def create_order(self):
        """
        Crea una orden de forma atómica. Esto asegura que si algo falla,
        toda la operación se revierte.
        """
        # 1. Validar que el carrito no esté vacío
        if not self.cart.items.exists():
            raise BusinessLogicError(detail="No se puede crear una orden con un carrito vacío.")

        # 2. Crear la orden inicial
        order = Order.objects.create(
            user=self.user,
            delivery_option=self.data.get('delivery_option'),
            delivery_address=self.data.get('delivery_address'),
            associated_appointment=self.data.get('associated_appointment'),
            total_amount=0 # Se calculará a continuación
        )

        total_amount = 0
        items_to_create = []

        # 3. Iterar sobre los ítems del carrito para crear los ítems de la orden
        for cart_item in self.cart.items.select_related('variant__product'):
            # Bloqueamos la variante para evitar race conditions en su stock
            variant = (
                ProductVariant.objects.select_for_update()
                .select_related('product')
                .get(pk=cart_item.variant_id)
            )

            if not variant.product.is_active:
                raise BusinessLogicError(detail=f"El producto '{variant.product.name}' está inactivo.")

            available = variant.stock - variant.reserved_stock
            if available < cart_item.quantity:
                raise BusinessLogicError(
                    detail=f"Stock insuficiente para la variante '{variant}'.",
                    internal_code="MKT-STOCK",
                )

            # Decidir qué precio usar (VIP o regular)
            price_at_purchase = variant.price
            if self.user.is_vip and variant.vip_price:
                price_at_purchase = variant.vip_price
            
            total_amount += price_at_purchase * cart_item.quantity
            
            items_to_create.append(
                OrderItem(
                    order=order,
                    variant=variant,
                    quantity=cart_item.quantity,
                    price_at_purchase=price_at_purchase
                )
            )
            
            variant.reserved_stock += cart_item.quantity
            variant.save(update_fields=['reserved_stock'])
            created_by = self.user if getattr(self.user, "is_authenticated", False) else None
            InventoryMovement.objects.create(
                variant=variant,
                quantity=cart_item.quantity,
                movement_type=InventoryMovement.MovementType.RESERVATION,
                reference_order=order,
                description="Reserva temporal de stock",
                created_by=created_by,
            )

        # 4. Crear todos los OrderItem en una sola consulta y actualizar el total
        OrderItem.objects.bulk_create(items_to_create)
        order.total_amount = total_amount
        order.wompi_transaction_id = f"ORDER-{order.id}-{uuid.uuid4().hex[:8]}"
        order.reservation_expires_at = timezone.now() + timedelta(minutes=30)
        order.save(update_fields=['total_amount', 'wompi_transaction_id', 'reservation_expires_at', 'updated_at'])

        # 5. Vaciar el carrito de compras
        self.cart.items.all().delete()
        
        return order


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
        Order.OrderStatus.SHIPPED: "ORDER_SHIPPED",
        Order.OrderStatus.DELIVERED: "ORDER_DELIVERED",
        Order.OrderStatus.CANCELLED: "ORDER_CANCELLED",
    }

    @classmethod
    @transaction.atomic
    def transition_to(cls, order, new_status, changed_by=None):
        current = order.status
        if current == new_status:
            return order
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise BusinessLogicError(
                detail=f"No se puede cambiar el estado de {current} a {new_status}.",
                internal_code="MKT-STATE",
            )

        order.status = new_status
        if new_status == Order.OrderStatus.DELIVERED:
            order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at', 'updated_at'])

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

        if new_status in cls.STATE_NOTIFICATION_EVENTS:
            try:
                notify_order_status_change.delay(str(order.id), new_status)
            except Exception:
                logger.exception("No se pudo notificar el cambio de estado de la orden %s", order.id)
        return order

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
    def confirm_payment(cls, order):
        cls._validate_pricing(order)
        cls._capture_stock(order)
        order.reservation_expires_at = None
        order.save(update_fields=['reservation_expires_at', 'updated_at'])
        return cls.transition_to(order, Order.OrderStatus.PAID)

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


class ReturnService:
    OFFER_EXPIRATION_DAYS = 365

    @classmethod
    @transaction.atomic
    def request_return(cls, order, items, reason):
        if order.status not in [
            Order.OrderStatus.PAID,
            Order.OrderStatus.DELIVERED,
        ]:
            raise BusinessLogicError(
                detail="La orden no se puede devolver en su estado actual.",
                internal_code="MKT-RETURN-STATE",
            )
        if not items:
            raise BusinessLogicError(detail="Debes seleccionar ítems a devolver.")

        settings_obj = GlobalSettings.load()
        delivered_date = order.delivered_at.date() if order.delivered_at else order.shipping_date
        if delivered_date and (timezone.now().date() - delivered_date).days > settings_obj.return_window_days:
            raise BusinessLogicError(
                detail="La orden excede la ventana de devoluciones permitida.",
                internal_code="MKT-RETURN-WINDOW",
            )

        payload = []
        order_items = {str(item.id): item for item in order.items.select_for_update()}

        for entry in items:
            item_id = str(entry['order_item_id'])
            quantity = entry['quantity']
            if item_id not in order_items:
                raise BusinessLogicError(detail="Uno de los ítems no pertenece a la orden.")
            order_item = order_items[item_id]
            available = order_item.quantity - order_item.quantity_returned
            if quantity <= 0 or quantity > available:
                raise BusinessLogicError(detail="La cantidad solicitada no es válida para un ítem.")
            payload.append({'order_item_id': item_id, 'quantity': quantity})

        order.status = Order.OrderStatus.RETURN_REQUESTED
        order.return_reason = reason
        order.return_requested_at = timezone.now()
        order.return_request_data = payload
        order.save(update_fields=['status', 'return_reason', 'return_requested_at', 'return_request_data', 'updated_at'])
        try:
            notify_order_status_change.delay(str(order.id))
        except Exception:
            logger.exception("No se pudo notificar la solicitud de devolución para la orden %s", order.id)
        return order

    @classmethod
    @transaction.atomic
    def process_return(cls, order, approved, processed_by):
        if order.status != Order.OrderStatus.RETURN_REQUESTED:
            raise BusinessLogicError(detail="La orden no tiene una devolución pendiente.")

        if not approved:
            order.status = Order.OrderStatus.RETURN_REJECTED
            order.return_request_data = []
            order.save(update_fields=['status', 'return_request_data', 'updated_at'])
            return order

        settings_obj = GlobalSettings.load()
        delivered_date = order.delivered_at.date() if order.delivered_at else order.shipping_date
        if delivered_date and (timezone.now().date() - delivered_date).days > settings_obj.return_window_days:
            raise BusinessLogicError(detail="La solicitud excede la ventana de devoluciones permitida.")

        OrderService.transition_to(order, Order.OrderStatus.RETURN_APPROVED, changed_by=processed_by)

        total_refund = Decimal('0')
        for entry in order.return_request_data:
            order_item = order.items.select_for_update().get(id=entry['order_item_id'])
            quantity = entry['quantity']
            if quantity <= 0:
                continue
            available = order_item.quantity - order_item.quantity_returned
            if quantity > available:
                raise BusinessLogicError(detail="La cantidad aprobada excede el total original del ítem.")

            order_item.quantity_returned += quantity
            order_item.save(update_fields=['quantity_returned'])

            variant = order_item.variant
            variant.stock += quantity
            variant.save(update_fields=['stock'])
            InventoryMovement.objects.create(
                variant=variant,
                quantity=quantity,
                movement_type=InventoryMovement.MovementType.RETURN,
                reference_order=order,
                description="Devolución aprobada",
                created_by=processed_by,
            )

            total_refund += order_item.price_at_purchase * quantity

        if total_refund > 0:
            expires = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
            ClientCredit.objects.create(
                user=order.user,
                originating_payment=None,
                initial_amount=total_refund,
                remaining_amount=total_refund,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires,
            )

        order.return_request_data = []
        order.save(update_fields=['return_request_data', 'updated_at'])
        OrderService.transition_to(order, Order.OrderStatus.REFUNDED, changed_by=processed_by)
        return order
