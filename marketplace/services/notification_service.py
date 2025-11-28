"""
Servicio de notificaciones para el módulo Marketplace.
"""
import logging

from django.conf import settings
from django.utils import timezone

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
        from ..models import Order

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
