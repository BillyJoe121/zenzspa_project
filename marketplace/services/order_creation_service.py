"""
Servicio para creación de órdenes a partir de carritos de compra.
"""
import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from decimal import Decimal

from django.conf import settings

from core.utils.exceptions import BusinessLogicError
from ..models import InventoryMovement, Order, OrderItem, ProductVariant

logger = logging.getLogger(__name__)

# Costo de envío a domicilio (configurable via settings)
SHIPPING_COST = Decimal(getattr(settings, 'SHIPPING_COST', '6500'))


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

        # Calcular fecha estimada de entrega
        max_prep_days = 0
        if self.cart.items.exists():
            max_prep_days = max(
                (item.variant.product.preparation_days for item in self.cart.items.all()),
                default=1
            )

        if self.data.get('delivery_option') == Order.DeliveryOptions.DELIVERY:
            max_prep_days += 3 # Días promedio de envío

        order.estimated_delivery_date = timezone.now().date() + timedelta(days=max_prep_days)
        order.save(update_fields=['estimated_delivery_date'])

        total_amount = 0
        items_to_create = []

        # 3. Iterar sobre los ítems del carrito para crear los ítems de la orden
        for cart_item in self.cart.items.select_related('variant__product'):
            # Bloquear variante y reservar stock de forma atómica
            variant = (
                ProductVariant.objects.select_for_update()
                .select_related('product')
                .get(pk=cart_item.variant_id)
            )

            if not variant.product.is_active:
                raise BusinessLogicError(detail=f"El producto '{variant.product.name}' está inactivo.")

            updated = ProductVariant.objects.filter(
                pk=variant.pk,
                reserved_stock__lte=F('stock') - cart_item.quantity,
            ).update(reserved_stock=F('reserved_stock') + cart_item.quantity)

            if updated == 0:
                raise BusinessLogicError(
                    detail=f"Stock insuficiente para la variante '{variant}'.",
                    internal_code="MKT-STOCK",
                )
            # Refrescar para movimientos/auditoría
            variant.refresh_from_db(fields=['reserved_stock', 'stock'])

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

            created_by = self.user if getattr(self.user, "is_authenticated", False) else None
            # Idempotencia: si ya existe movimiento de reserva para esta orden+variante, no duplicar
            InventoryMovement.objects.get_or_create(
                variant=variant,
                reference_order=order,
                movement_type=InventoryMovement.MovementType.RESERVATION,
                defaults={
                    "quantity": cart_item.quantity,
                    "description": "Reserva temporal de stock",
                    "created_by": created_by,
                },
            )

        # 4. Crear todos los OrderItem en una sola consulta y actualizar el total
        OrderItem.objects.bulk_create(items_to_create)
        
        # 5. Agregar costo de envío si es entrega a domicilio
        shipping_cost = Decimal('0')
        if self.data.get('delivery_option') == Order.DeliveryOptions.DELIVERY:
            shipping_cost = SHIPPING_COST
            total_amount += shipping_cost
            logger.info(
                "Costo de envío agregado: order_id=%s, shipping=%s",
                order.id, shipping_cost
            )
        
        order.total_amount = total_amount
        order.shipping_cost = shipping_cost
        order.reservation_expires_at = timezone.now() + timedelta(minutes=30)
        order.save(update_fields=['total_amount', 'shipping_cost', 'reservation_expires_at', 'updated_at'])

        # 6. Vaciar el carrito inmediatamente después de crear la orden
        # Esto previene que el carrito se acumule si el usuario crea múltiples órdenes
        deleted_count = self.cart.items.all().delete()[0]
        logger.info(
            "Carrito vaciado después de crear orden: user=%s, order=%s, items_deleted=%d",
            self.user.id, order.id, deleted_count
        )

        logger.info(
            "Orden creada: order_id=%s, user=%s, total=%s, items=%d",
            order.id, self.user.id, order.total_amount, len(items_to_create)
        )
        return order
