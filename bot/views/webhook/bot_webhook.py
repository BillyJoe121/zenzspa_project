"""
Vista principal del webhook del bot para mensajes web.
Actúa como contenedor para mantener compatibilidad con imports existentes.
"""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ...throttling import BotDailyThrottle, BotIPThrottle, BotRateThrottle
from .bot_webhook_processing import BotWebhookProcessingMixin
from .bot_webhook_security import BotWebhookSecurityMixin


class BotWebhookView(BotWebhookSecurityMixin, BotWebhookProcessingMixin, APIView):
    permission_classes = [AllowAny]  # Soporte para usuarios anónimos y registrados
    # CORRECCIÓN CRÍTICA: Aplicar throttle por minuto Y diario
    # MEJORA #4: Agregar throttle por IP para prevenir abuso con múltiples cuentas
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def post(self, request):
        context = self.prepare_request_context(request)
        if isinstance(context, Response):
            return context

        async_response = self.handle_async_mode(request, context)
        if async_response:
            return async_response

        return self.process_sync_flow(context)


__all__ = ["BotWebhookView"]
