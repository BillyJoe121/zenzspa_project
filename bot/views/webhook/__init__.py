"""
Módulo de webhooks del bot.

Exporta las vistas principales para mantener compatibilidad con imports existentes.
"""
from .bot_webhook import BotWebhookView
from .health_check import BotHealthCheckView
from .whatsapp_webhook import WhatsAppWebhookView

__all__ = [
    'BotWebhookView',
    'BotHealthCheckView',
    'WhatsAppWebhookView',
]
