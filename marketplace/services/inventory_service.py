"""
Servicio de gestión de inventario para Marketplace.
"""
from .notification_service import MarketplaceNotificationService


class InventoryService:
    @staticmethod
    def check_low_stock(variant):
        if variant.stock <= variant.low_stock_threshold:
            # En un sistema real, usaríamos cache para no spammear alertas
            # Por ahora, enviamos alerta directa
            MarketplaceNotificationService.send_low_stock_alert([variant])
