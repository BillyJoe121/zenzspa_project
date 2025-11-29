"""
Servicio para gestión de devoluciones de órdenes.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from core.models import AuditLog, GlobalSettings
from ..models import InventoryMovement, Order
from ..tasks import notify_order_status_change
from .notification_service import MarketplaceNotificationService
from .order_service import OrderService

logger = logging.getLogger(__name__)


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
            from finances.services import FinancialAdjustmentService
            from finances.models import FinancialAdjustment

            FinancialAdjustmentService.create_adjustment(
                user=order.user,
                amount=total_refund,
                adjustment_type=FinancialAdjustment.AdjustmentType.CREDIT,
                reason=f"Devolución orden #{order.id}",
                created_by=processed_by,
                related_payment=None # Opcional: Podríamos buscar el pago original si fuera necesario
            )
            
            cls._notify_return_processed(order, total_refund)
            cls._log_return_audit(order, processed_by, total_refund, refunded_items)

        order.return_request_data = []
        order.save(update_fields=['return_request_data', 'updated_at'])
        OrderService.transition_to(order, Order.OrderStatus.REFUNDED, changed_by=processed_by)
        return order

    @staticmethod
    def _notify_return_processed(order, credited_amount):
        MarketplaceNotificationService.send_credit_issued(order, credited_amount, "Devolución de productos")

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
