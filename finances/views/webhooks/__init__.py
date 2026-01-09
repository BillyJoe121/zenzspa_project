"""
Views de Webhooks de Wompi.

Endpoints para recibir y procesar webhooks:
- Webhook principal de transacciones
- Confirmación manual (desarrollo local)
"""
import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from finances.models import Payment, WebhookEvent
from finances.webhooks import WompiWebhookService


logger = logging.getLogger(__name__)


class WompiWebhookView(generics.GenericAPIView):
    """
    Endpoint para recibir webhooks de Wompi.
    Migrado desde spa.views.packages para centralizar lógica de pagos.

    POST /api/finances/webhooks/wompi/
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            webhook_service = WompiWebhookService(request.data, headers=request.headers)
            event_type = webhook_service.event_type

            if event_type == "transaction.updated":
                result = webhook_service.process_transaction_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            if event_type in {"nequi_token.updated", "bancolombia_transfer_token.updated"}:
                result = webhook_service.process_token_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            if event_type in {"transfer.updated", "payout.updated"}:
                result = webhook_service.process_payout_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            webhook_service._update_event_status(WebhookEvent.Status.IGNORED, "Evento no manejado.")
            return Response({"status": "event_type_not_handled"}, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Error interno del servidor al procesar el webhook."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WompiManualConfirmView(generics.GenericAPIView):
    """
    Endpoint para confirmar pagos manualmente cuando el widget modal
    no redirige y Wompi no envía webhook (desarrollo local).
    
    POST /api/finances/webhooks/wompi/manual-confirm/
    Body: {
        "transaction_id": "12001854-176712619B-56986",
        "reference": "PAY-396de01fb41",
        "status": "APPROVED"
    }
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transaction_id = request.data.get('transaction_id')
        reference = request.data.get('reference')
        transaction_status = request.data.get('status', 'APPROVED')
        
        if not transaction_id:
            return Response(
                {"error": "transaction_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"[MANUAL-CONFIRM] Confirmando pago: {transaction_id}")
        
        try:
            # Buscar el pago por transaction_id
            # El reference de Wompi se guarda como transaction_id en nuestro modelo
            payment = Payment.objects.filter(transaction_id=reference).first()
            
            if not payment:
                logger.error(f"[MANUAL-CONFIRM] Pago no encontrado con reference: {reference}")
                return Response(
                    {"error": "Pago no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Construir payload simulado de Wompi
            transaction_payload = {
                "id": transaction_id,
                "reference": reference,
                "status": transaction_status,
                "payment_method_type": "CARD",
            }
            
            # Usar PaymentService para aplicar el estado
            # Esto ejecutará toda la lógica: actualizar cita, crear comisión, etc.
            from finances.payments import PaymentService
            final_status = PaymentService.apply_gateway_status(
                payment=payment,
                gateway_status=transaction_status,
                transaction_payload=transaction_payload
            )
            
            logger.info(f"[MANUAL-CONFIRM] Pago actualizado: {payment.id} -> {final_status}")
            
            return Response({
                "status": "success",
                "payment_id": str(payment.id),
                "payment_status": final_status
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"[MANUAL-CONFIRM] Error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return Response(
                {"error": f"Error al confirmar pago: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
