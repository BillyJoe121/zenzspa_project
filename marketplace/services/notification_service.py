"""
Servicio de notificaciones para el módulo Marketplace.
"""
import logging

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

        event_code, context = cls.get_event_payload(order, new_status)

        if not event_code:
            return

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
    def get_event_payload(cls, order, new_status):
        """
        Devuelve el event_code y contexto especializado (si aplica)
        para la notificación de estado de orden.
        """
        event_code, context = cls._build_event_payload(order, new_status)
        return event_code, context

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
    def send_credit_issued(cls, order, amount, reason):
        """
        Envía notificación de crédito emitido (por devolución u otro motivo).
        """
        user = order.user
        if not user:
            return

        try:
            NotificationService.send_notification(
                user=user,
                event_code="ORDER_CREDIT_ISSUED",
                context={
                    "user_name": user.get_full_name() or user.first_name or "Cliente",
                    "credit_amount": f"${amount:,.0f}",
                    "reason": reason,
                    "order_id": str(order.id),
                },
                priority="high"
            )
            logger.info("Notificación de crédito enviada: order_id=%s, amount=%s", order.id, amount)
        except Exception as e:
                logger.error("Error enviando notificación de crédito %s: %s", order.id, e)

    @classmethod
    def _build_event_payload(cls, order, new_status):
        from ..models import Order

        user = order.user
        if not user:
            return None, None

        base_context = {
            "user_name": user.get_full_name() or user.first_name or "Cliente",
            "order_id": str(order.id),
        }

        ready_for_pickup = getattr(Order.OrderStatus, "READY_FOR_PICKUP", None)
        if ready_for_pickup and new_status == ready_for_pickup:
            base_context.update({
                "store_address": "Carrera 64 #1c-87",
                "pickup_code": cls._build_pickup_code(order),
            })
            return "ORDER_READY_FOR_PICKUP", base_context

        if new_status == Order.OrderStatus.CANCELLED:
            base_context.update({
                "cancellation_reason": cls._resolve_cancellation_reason(order),
            })
            return "ORDER_CANCELLED", base_context

        return None, None

    @staticmethod
    def _build_pickup_code(order):
        pickup_code = getattr(order, "pickup_code", None)
        if pickup_code:
            return str(pickup_code)
        return str(order.id)

    @staticmethod
    def _resolve_cancellation_reason(order):
        candidates = [
            getattr(order, "cancellation_reason", None),
            getattr(order, "return_reason", None),
            getattr(order, "fraud_reason", None),
        ]
        for reason in candidates:
            if reason:
                return reason
        return "Motivo no especificado."
