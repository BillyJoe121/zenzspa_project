import logging
import uuid
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

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
            raise ValueError("No se puede crear una orden con un carrito vacío.")

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
                raise ValueError(f"El producto '{variant.product.name}' está inactivo.")

            # Validar stock una última vez
            if variant.stock < cart_item.quantity:
                raise ValueError(f"Stock insuficiente para la variante '{variant}'.")

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
            
            # Actualizar el stock de la variante
            variant.stock -= cart_item.quantity
            if variant.stock < 0:
                raise ValueError("El stock no puede ser negativo.")
            variant.save(update_fields=['stock'])
            created_by = self.user if getattr(self.user, "is_authenticated", False) else None
            InventoryMovement.objects.create(
                variant=variant,
                quantity=-cart_item.quantity,
                movement_type=InventoryMovement.MovementType.SALE,
                reference_order=order,
                description="Venta en checkout",
                created_by=created_by,
            )

        # 4. Crear todos los OrderItem en una sola consulta y actualizar el total
        OrderItem.objects.bulk_create(items_to_create)
        order.total_amount = total_amount
        order.wompi_transaction_id = f"ORDER-{order.id}-{uuid.uuid4().hex[:8]}"
        order.save(update_fields=['total_amount', 'wompi_transaction_id', 'updated_at'])

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

    @classmethod
    @transaction.atomic
    def transition_to(cls, order, new_status, changed_by=None):
        current = order.status
        if current == new_status:
            return order
        allowed = cls.ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValueError(f"No se puede cambiar el estado de {current} a {new_status}.")

        order.status = new_status
        if new_status == Order.OrderStatus.DELIVERED:
            order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at', 'updated_at'])
        try:
            notify_order_status_change.delay(str(order.id))
        except Exception:
            logger.exception("No se pudo notificar el cambio de estado de la orden %s", order.id)
        return order


class ReturnService:
    OFFER_EXPIRATION_DAYS = 365

    @classmethod
    @transaction.atomic
    def request_return(cls, order, items, reason):
        if order.status not in [
            Order.OrderStatus.PAID,
            Order.OrderStatus.DELIVERED,
        ]:
            raise ValueError("La orden no se puede devolver en su estado actual.")
        if not items:
            raise ValueError("Debes seleccionar ítems a devolver.")

        payload = []
        order_items = {str(item.id): item for item in order.items.select_for_update()}

        for entry in items:
            item_id = str(entry['order_item_id'])
            quantity = entry['quantity']
            if item_id not in order_items:
                raise ValueError("Uno de los ítems no pertenece a la orden.")
            order_item = order_items[item_id]
            available = order_item.quantity - order_item.quantity_returned
            if quantity <= 0 or quantity > available:
                raise ValueError("La cantidad solicitada no es válida para un ítem.")
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
            raise ValueError("La orden no tiene una devolución pendiente.")

        if not approved:
            order.status = Order.OrderStatus.RETURN_REJECTED
            order.return_request_data = []
            order.save(update_fields=['status', 'return_request_data', 'updated_at'])
            return order

        settings_obj = GlobalSettings.load()
        delivered_date = order.delivered_at.date() if order.delivered_at else order.shipping_date
        if delivered_date and (timezone.now().date() - delivered_date).days > settings_obj.return_window_days:
            raise ValueError("La solicitud excede la ventana de devoluciones permitida.")

        OrderService.transition_to(order, Order.OrderStatus.RETURN_APPROVED, changed_by=processed_by)

        total_refund = Decimal('0')
        for entry in order.return_request_data:
            order_item = order.items.select_for_update().get(id=entry['order_item_id'])
            quantity = entry['quantity']
            if quantity <= 0:
                continue
            available = order_item.quantity - order_item.quantity_returned
            if quantity > available:
                raise ValueError("La cantidad aprobada excede el total original del ítem.")

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
