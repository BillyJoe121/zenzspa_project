import logging
import uuid
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from core.models import AuditLog, GlobalSettings
from spa.models import ClientCredit
from .models import Order, OrderItem, ProductVariant, InventoryMovement
from marketplace.tasks import notify_order_status_change
from notifications.services import NotificationService

logger = logging.getLogger(__name__)

class MarketplaceNotificationService:
    """
    Servicio de notificaciones para el módulo Marketplace.
    Migrado al sistema centralizado de NotificationService.
    """

    @classmethod
    def send_order_status_update(cls, order, new_status):
        """
        Envía notificación de actualización de estado de orden.
        Usa el sistema centralizado de notificaciones con templates aprobados.
        """
        user = order.user
        if not user:
            logger.warning("Orden %s no tiene usuario asociado", order.id)
            return

        # Determinar qué event_code usar según el estado
        event_code = None
        context = {
            "user_name": user.get_full_name() or user.first_name or "Cliente",
            "order_id": str(order.id),
        }

        if new_status == Order.OrderStatus.SHIPPED:
            event_code = "ORDER_SHIPPED"
            context.update({
                "tracking_number": order.tracking_number or "Pendiente",
                "estimated_delivery": order.estimated_delivery_date.strftime("%d de %B") if order.estimated_delivery_date else "Por confirmar",
            })
        elif new_status == Order.OrderStatus.DELIVERED:
            event_code = "ORDER_DELIVERED"
            context.update({
                "delivery_date": order.delivered_at.strftime("%d de %B") if order.delivered_at else timezone.now().strftime("%d de %B"),
            })
        elif new_status == getattr(Order.OrderStatus, "READY_FOR_PICKUP", None):
            event_code = "ORDER_READY_FOR_PICKUP"
            context.update({
                "store_address": getattr(settings, 'STORE_ADDRESS', 'Nuestro local'),
                "store_hours": getattr(settings, 'STORE_HOURS', 'Lunes a Sábado 9AM - 6PM'),
                "pickup_code": str(order.id)[-6:],  # Últimos 6 dígitos como código
            })

        if event_code:
            try:
                NotificationService.send_notification(
                    user=user,
                    event_code=event_code,
                    context=context,
                    priority="high"
                )
                logger.info("Notificación de orden enviada: order_id=%s, event=%s", order.id, event_code)
            except Exception as e:
                logger.error("Error enviando notificación de orden %s: %s", order.id, e)

    @classmethod
    def send_low_stock_alert(cls, variants):
        """
        Envía alerta de stock bajo a los administradores.
        Usa el sistema centralizado de notificaciones con templates aprobados.
        """
        from bot.models import BotConfiguration
        from users.models import CustomUser

        bot_config = BotConfiguration.objects.filter(is_active=True).first()
        admin_phone = bot_config.admin_phone if bot_config else None

        if not admin_phone:
            logger.warning("No hay número de admin configurado para alertas de stock")
            return

        # Buscar usuario admin con ese teléfono
        admin_user = CustomUser.objects.filter(
            phone_number=admin_phone,
            is_staff=True
        ).first()

        if not admin_user:
            # Fallback: buscar cualquier admin
            admin_user = CustomUser.objects.filter(is_staff=True, is_active=True).first()

        if not admin_user:
            logger.warning("No se encontró usuario admin para enviar alerta de stock")
            return

        # Formatear lista de productos
        items_list = "\n".join([
            f"- {v.product.name} ({v.name}): {v.stock} unid."
            for v in variants
        ])

        try:
            NotificationService.send_notification(
                user=admin_user,
                event_code="STOCK_LOW_ALERT",
                context={
                    "items_list": items_list,
                },
                priority="high"
            )
            logger.info("Alerta de stock bajo enviada: %d productos", len(variants))
        except Exception as e:
            logger.error("Error enviando alerta de stock bajo: %s", e)

    @classmethod
    def send_return_processed(cls, order, amount):
        """
        Envía notificación de devolución procesada.
        Usa el sistema centralizado de notificaciones con templates aprobados.
        """
        user = order.user
        if not user:
            logger.warning("Orden %s no tiene usuario para notificar devolución", order.id)
            return

        try:
            NotificationService.send_notification(
                user=user,
                event_code="ORDER_CREDIT_ISSUED",
                context={
                    "user_name": user.get_full_name() or user.first_name or "Cliente",
                    "credit_amount": f"{amount:,.0f}",
                    "reason": "Devolución de productos",
                    "order_id": str(order.id),
                },
                priority="high"
            )
            logger.info("Notificación de devolución enviada: order_id=%s, amount=%s", order.id, amount)
        except Exception as e:
            logger.error("Error enviando notificación de devolución %s: %s", order.id, e)

class InventoryService:
    @staticmethod
    def check_low_stock(variant):
        if variant.stock <= variant.low_stock_threshold:
            # En un sistema real, usaríamos cache para no spammear alertas
            # Por ahora, enviamos alerta directa
            MarketplaceNotificationService.send_low_stock_alert([variant])


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
        
        logger.info(
            "Orden creada: order_id=%s, user=%s, total=%s, items=%d",
            order.id, self.user.id, order.total_amount, len(items_to_create)
        )
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

        cls._capture_stock(order)
        order.reservation_expires_at = None
        order.save(update_fields=['reservation_expires_at', 'updated_at'])
        
        logger.info(
            "Pago confirmado: order_id=%s, user=%s, total=%s",
            order.id, order.user.id, order.total_amount
        )

        if order.status == Order.OrderStatus.CANCELLED:
            order.status = Order.OrderStatus.PAID
            order.save(update_fields=['status', 'updated_at'])
            return order
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
            InventoryService.check_low_stock(variant)


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
        
        if not order.delivered_at:
            raise BusinessLogicError(detail="La orden no ha sido entregada aún.")
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
            notify_order_status_change.delay(str(order.id), Order.OrderStatus.RETURN_REQUESTED)
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
        refunded_items = []
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
            variant_label = variant.sku or str(variant)
            refunded_items.append(f"{variant_label} x {quantity}")

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
            cls._notify_return_processed(order, total_refund)
            cls._log_return_audit(order, processed_by, total_refund, refunded_items)

        order.return_request_data = []
        order.save(update_fields=['return_request_data', 'updated_at'])
        OrderService.transition_to(order, Order.OrderStatus.REFUNDED, changed_by=processed_by)
        return order

    @staticmethod
    def _notify_return_processed(order, credited_amount):
        MarketplaceNotificationService.send_return_processed(order, credited_amount)

    @staticmethod
    def _log_return_audit(order, processed_by, credited_amount, refunded_items):
        items_summary = ", ".join(refunded_items) if refunded_items else "Sin detalle de ítems"
        details = (
            f"order_id={order.id}; "
            f"items={items_summary}; "
            f"credited_amount={format(credited_amount, '.2f')}"
        )
        AuditLog.objects.create(
            action=AuditLog.Action.MARKETPLACE_RETURN,
            admin_user=processed_by,
            target_user=order.user,
            details=details,
        )
