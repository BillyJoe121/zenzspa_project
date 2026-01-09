"""
Views de Wompi Payouts API - Endpoints Admin.

Endpoints para gestión de dispersiones/pagos salientes:
- Consulta de cuentas origen
- Lista de bancos soportados
- Consulta de saldo
- Recarga sandbox (testing)
- Webhook de payouts
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminUser, IsStaffOrAdmin
from core.models import AuditLog
from finances.models import CommissionLedger
from finances.payouts import WompiPayoutsClient, WompiPayoutsError
from finances.webhooks.payouts import WompiPayoutsWebhookService


logger = logging.getLogger(__name__)


class WompiPayoutsAccountsView(APIView):
    """
    Consulta las cuentas origen disponibles para dispersión en Wompi.

    GET /api/v1/finances/wompi-payouts/accounts/

    Response:
    {
        "accounts": [
            {
                "id": "uuid",
                "balanceInCents": 1000000,
                "accountNumber": "1234567890",
                "bankId": "1007",
                "accountType": "AHORROS",
                "status": "ACTIVE"
            }
        ],
        "mode": "sandbox"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        try:
            client = WompiPayoutsClient()
            accounts = client.get_accounts()

            return Response({
                "accounts": accounts,
                "mode": settings.WOMPI_PAYOUT_MODE,
                "total_accounts": len(accounts)
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando cuentas de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsBanksView(APIView):
    """
    Consulta la lista de bancos soportados por Wompi para dispersión.

    GET /api/v1/finances/wompi-payouts/banks/

    Response:
    {
        "banks": [
            {
                "id": "1007",
                "name": "BANCOLOMBIA",
                "code": "1007"
            },
            ...
        ],
        "total_banks": 50
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        try:
            client = WompiPayoutsClient()
            banks = client.get_banks()

            return Response({
                "banks": banks,
                "total_banks": len(banks)
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando bancos de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsBalanceView(APIView):
    """
    Consulta el saldo disponible en la cuenta de dispersión.

    GET /api/v1/finances/wompi-payouts/balance/

    Query params:
    - account_id (opcional): ID de cuenta específica

    Response:
    {
        "balance": "10000.00",
        "currency": "COP",
        "account_id": "uuid",
        "mode": "sandbox"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        account_id = request.query_params.get('account_id')

        try:
            client = WompiPayoutsClient()
            balance = client.get_available_balance(account_id=account_id)

            return Response({
                "balance": str(balance),
                "currency": "COP",
                "account_id": account_id or "default",
                "mode": settings.WOMPI_PAYOUT_MODE
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando saldo de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsRechargeView(APIView):
    """
    Recarga saldo en cuenta de sandbox (solo para testing).

    POST /api/v1/finances/wompi-payouts/sandbox/recharge/

    Body:
    {
        "account_id": "uuid",
        "amount": "100000.00"
    }

    Response:
    {
        "success": true,
        "account_id": "uuid",
        "amount": "100000.00",
        "message": "Saldo recargado exitosamente"
    }
    """
    permission_classes = [IsAuthenticated, IsAdminUser]  # Solo superadmin

    def post(self, request):
        # Solo permitir en sandbox
        if settings.WOMPI_PAYOUT_MODE != "sandbox":
            return Response(
                {"error": "La recarga de saldo solo está disponible en modo sandbox"},
                status=status.HTTP_403_FORBIDDEN
            )

        account_id = request.data.get('account_id')
        amount = request.data.get('amount')

        if not account_id or not amount:
            return Response(
                {"error": "Se requieren account_id y amount"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            amount_decimal = Decimal(str(amount))

            if amount_decimal <= 0:
                return Response(
                    {"error": "El monto debe ser mayor a cero"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            client = WompiPayoutsClient()
            result = client.recharge_balance_sandbox(account_id, amount_decimal)

            # Log de auditoría
            AuditLog.objects.create(
                admin_user=request.user,
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details=f"Recarga sandbox Wompi: ${amount_decimal} COP en cuenta {account_id}"
            )

            return Response({
                "success": True,
                "account_id": account_id,
                "amount": str(amount_decimal),
                "message": "Saldo recargado exitosamente",
                "result": result
            })

        except (ValueError, Decimal.InvalidOperation):
            return Response(
                {"error": "Monto inválido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except WompiPayoutsError as exc:
            logger.exception("Error recargando saldo en Wompi Sandbox")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsWebhookView(APIView):
    """
    Webhook endpoint para recibir eventos de Wompi Payouts API.

    POST /api/v1/finances/wompi-payouts/webhook/

    Wompi envía eventos cuando cambia el estado de un payout o transacción.

    Eventos soportados:
    - payout.updated: Cambio de estado en un lote de pago
    - transaction.updated: Cambio de estado en una transacción individual

    Headers esperados:
    - X-Signature: Firma HMAC SHA256 del payload con WOMPI_PAYOUT_EVENTS_SECRET

    Payload de ejemplo:
    {
        "event": "transaction.updated",
        "data": {
            "id": "transaction-uuid",
            "status": "APPROVED",
            "reference": "DEV-COMM-20251231-120000",
            "amount": 5000000,
            "payoutId": "payout-uuid"
        }
    }
    """
    permission_classes = [AllowAny]  # Wompi no puede autenticarse

    def post(self, request):
        # Extraer firma del header
        signature = request.META.get('HTTP_X_SIGNATURE', '')

        if not signature:
            logger.warning("[Wompi Payouts Webhook] Request sin firma X-Signature")
            return Response(
                {"error": "Missing X-Signature header"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Validar firma
        if not WompiPayoutsWebhookService.validate_signature(request.data, signature):
            logger.warning(
                "[Wompi Payouts Webhook] Firma inválida. Posible intento de falsificación."
            )
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Extraer tipo de evento
        event_type = request.data.get('event')

        if not event_type:
            logger.error("[Wompi Payouts Webhook] Payload sin campo 'event'")
            return Response(
                {"error": "Missing event type"},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(
            "[Wompi Payouts Webhook] Recibido evento: %s",
            event_type
        )

        try:
            # Procesar evento
            result = WompiPayoutsWebhookService.process_event(event_type, request.data)

            return Response(
                {
                    "status": "webhook_processed",
                    "event_type": event_type,
                    "result": result
                },
                status=status.HTTP_200_OK
            )

        except Exception as exc:
            logger.exception(
                "[Wompi Payouts Webhook] Error procesando evento %s: %s",
                event_type,
                exc
            )
            # Retornar 200 para que Wompi no reintente
            # (el error ya está loggeado para revisión manual)
            return Response(
                {
                    "status": "error",
                    "message": "Internal error processing webhook",
                    "event_type": event_type
                },
                status=status.HTTP_200_OK
            )
