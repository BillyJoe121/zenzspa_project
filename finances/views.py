"""
Views para el módulo finances.

Incluye endpoints de:
- Comisiones del desarrollador
- Iniciación de pagos (appointments, VIP, packages)
- Webhook de Wompi
- Instituciones financieras PSE
"""
import uuid
from decimal import Decimal
import requests

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminUser, IsStaffOrAdmin, IsVerified
from core.models import AuditLog, GlobalSettings
from spa.models import Appointment
from .services import DeveloperCommissionService, WompiDisbursementClient
from .models import ClientCredit, CommissionLedger, Payment, WebhookEvent
from .serializers import ClientCreditAdminSerializer, CommissionLedgerSerializer, ClientCreditSerializer, PaymentSerializer
from .gateway import WompiPaymentClient, build_integrity_signature
from .webhooks import WompiWebhookService
from spa.serializers import PackagePurchaseCreateSerializer
from .payments import PaymentService


class CommissionLedgerListView(generics.ListAPIView):
    """
    Lista los asientos del libro de comisiones para conciliación.
    Permite filtrar por estado y rango de fechas.
    """

    serializer_class = CommissionLedgerSerializer
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]
    queryset = CommissionLedger.objects.select_related("source_payment").order_by("-created_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        return queryset


class DeveloperCommissionStatusView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        settings_obj = GlobalSettings.load()
        debt = DeveloperCommissionService.get_developer_debt()
        balance_str = "0.00"
        client = WompiDisbursementClient()
        try:
            balance = client.get_available_balance()
            balance_str = str(balance.quantize(Decimal("0.01")))
        except Exception:
            balance_str = "0.00"
        data = {
            "developer_debt": str(debt),
            "payout_threshold": str(settings_obj.developer_payout_threshold),
            "developer_in_default": settings_obj.developer_in_default,
            "developer_default_since": (
                settings_obj.developer_default_since.isoformat()
                if settings_obj.developer_default_since
                else None
            ),
            "wompi_available_balance": balance_str,
        }
        return Response(data)


class PSEFinancialInstitutionsView(APIView):
    """
    Lista las instituciones financieras disponibles para PSE.

    GET /api/finances/pse-banks/

    Response:
        {
            "data": [
                {
                    "financial_institution_code": "1022",
                    "financial_institution_name": "BANCO UNION COLOMBIANO"
                },
                ...
            ]
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client = WompiPaymentClient()
        try:
            result = client.get_pse_financial_institutions()

            # La función de gateway devuelve actualmente solo la lista; soporta tuplas por si cambia.
            if isinstance(result, tuple) and len(result) == 2:
                institutions_data, status_code = result
            else:
                institutions_data = result
                status_code = 200

            if status_code == 200:
                return Response(institutions_data, status=200)
            else:
                return Response(
                    {"error": "No se pudieron obtener los bancos PSE"},
                    status=status_code
                )
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response else 502
            return Response(
                {"error": "Error al consultar bancos PSE", "detail": str(exc)},
                status=status_code,
            )
        except Exception as e:
            return Response(
                {"error": f"Error al consultar bancos PSE: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class InitiateAppointmentPaymentView(generics.GenericAPIView):
    """
    Inicia el flujo de pago para una cita pendiente.
    Migrado desde spa.views.packages para centralizar lógica de pagos.

    GET /api/finances/payments/appointment/<pk>/initiate/
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request, pk):
        appointment = generics.get_object_or_404(Appointment, pk=pk, user=request.user)

        if appointment.status != Appointment.AppointmentStatus.PENDING_PAYMENT:
            return Response(
                {"error": "Esta cita no tiene un pago de anticipo pendiente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener el tipo de pago desde query params (deposit o full)
        payment_type = request.query_params.get('payment_type', 'deposit')
        
        # Calcular el monto según el tipo de pago
        total_price = appointment.price_at_purchase
        
        if payment_type == 'full':
            # Pago total
            amount = total_price
            payment_type_enum = Payment.PaymentType.FINAL
        else:
            # Pago de anticipo (40% por defecto)
            global_settings = GlobalSettings.load()
            advance_percentage = Decimal(global_settings.advance_payment_percentage / 100)
            amount = total_price * advance_percentage
            payment_type_enum = Payment.PaymentType.ADVANCE

        # Buscar o crear el pago pendiente
        try:
            payment = appointment.payments.get(
                status=Payment.PaymentStatus.PENDING,
                payment_type=payment_type_enum
            )
            # Actualizar el monto si cambió
            payment.amount = amount
            payment.save()
        except Payment.DoesNotExist:
            # Crear nuevo pago con el tipo correcto
            payment = Payment.objects.create(
                user=request.user,
                appointment=appointment,
                amount=amount,
                payment_type=payment_type_enum,
                status=Payment.PaymentStatus.PENDING
            )

        amount_in_cents = int(payment.amount * 100)
        # Acortar referencia para evitar truncamiento en URL de Wompi
        reference = f"PAY-{str(payment.id)[-12:]}"
        payment.transaction_id = reference
        payment.save()

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


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


class InitiateVipSubscriptionView(generics.GenericAPIView):
    """
    Inicia el flujo de pago para suscripción VIP.
    Migrado desde spa.views.packages para centralizar lógica de suscripciones.

    POST /api/finances/payments/vip-subscription/initiate/
    """
    permission_classes = [IsAuthenticated, IsVerified]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        global_settings = GlobalSettings.load()
        vip_price = global_settings.vip_monthly_price

        if vip_price is None or vip_price <= 0:
            return Response(
                {"error": "El precio de la membresía VIP no está configurado en el sistema."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        reference = f"VIP-{user.id}-{uuid.uuid4().hex[:8]}"
        amount_in_cents = int(vip_price * 100)

        Payment.objects.create(
            user=user,
            amount=vip_price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.VIP_SUBSCRIPTION,
            transaction_id=reference
        )

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class InitiatePackagePurchaseView(generics.CreateAPIView):
    """
    Inicia el flujo de pago para la compra de un paquete.
    Migrado desde spa.views.packages para centralizar lógica de pagos.
    
    POST /api/finances/payments/package/initiate/
    """
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = PackagePurchaseCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        package = serializer.validated_data['package']
        user = request.user

        # Usar el servicio centralizado para crear el pago
        from finances.payments import PaymentService
        payment = PaymentService.create_package_payment(user, package)
        
        amount_in_cents = int(payment.amount * 100)
        reference = payment.transaction_id

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class BasePaymentCreationView(APIView):
    """Helper base class para crear transacciones Wompi a partir de un Payment existente."""

    permission_classes = [IsAuthenticated, IsVerified]
    payment_method = None  # override

    def get_payment(self, request, pk):
        try:
            return Payment.objects.get(pk=pk, user=request.user, status=Payment.PaymentStatus.PENDING)
        except Payment.DoesNotExist:
            return None

    def bad_request(self, message):
        return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


class CreatePSEPaymentView(BasePaymentCreationView):
    """Crea transacción PSE server-side."""
    payment_method = "PSE"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        required_fields = [
            "user_type",
            "user_legal_id",
            "user_legal_id_type",
            "financial_institution_code",
            "payment_description",
        ]
        for field in required_fields:
            if not data.get(field):
                return self.bad_request(f"Falta el campo requerido: {field}")

        response_data, status_code = PaymentService.create_pse_payment(
            payment=payment,
            user_type=int(data["user_type"]),
            user_legal_id=str(data["user_legal_id"]),
            user_legal_id_type=str(data["user_legal_id_type"]),
            financial_institution_code=str(data["financial_institution_code"]),
            payment_description=str(data["payment_description"]),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateNequiPaymentView(BasePaymentCreationView):
    """Crea transacción Nequi server-side."""
    payment_method = "NEQUI"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        phone_number = data.get("phone_number")
        if not phone_number:
            return self.bad_request("Falta el campo requerido: phone_number")

        response_data, status_code = PaymentService.create_nequi_payment(
            payment=payment,
            phone_number=str(phone_number),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateDaviplataPaymentView(BasePaymentCreationView):
    """Crea transacción Daviplata server-side."""
    payment_method = "DAVIPLATA"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        phone_number = data.get("phone_number")
        if not phone_number:
            return self.bad_request("Falta el campo requerido: phone_number")

        response_data, status_code = PaymentService.create_daviplata_payment(
            payment=payment,
            phone_number=str(phone_number),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateBancolombiaTransferPaymentView(BasePaymentCreationView):
    """Crea transacción Bancolombia Transfer server-side (botón)."""
    payment_method = "BANCOLOMBIA_TRANSFER"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        payment_description = data.get("payment_description")
        if not payment_description:
            return self.bad_request("Falta el campo requerido: payment_description")

        response_data, status_code = PaymentService.create_bancolombia_transfer_payment(
            payment=payment,
            payment_description=str(payment_description),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class ClientCreditAdminViewSet(viewsets.ModelViewSet):
    """
    CRUD administrativo para créditos de clientes.
    Permite ajustar saldo disponible tras reembolsos en efectivo u otros casos.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = ClientCreditAdminSerializer
    queryset = ClientCredit.objects.select_related("user", "originating_payment").order_by("-created_at")

    def _compute_status(self, credit: ClientCredit) -> str:
        # Marcar expirado si la fecha ya pasó
        if credit.expires_at and credit.expires_at < timezone.now().date():
            return ClientCredit.CreditStatus.EXPIRED
        if credit.remaining_amount == 0:
            return ClientCredit.CreditStatus.USED
        if credit.remaining_amount < credit.initial_amount:
            return ClientCredit.CreditStatus.PARTIALLY_USED
        return ClientCredit.CreditStatus.AVAILABLE

    def perform_create(self, serializer):
        credit = serializer.save()
        credit.status = self._compute_status(credit)
        credit.save(update_fields=["status"])
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=credit.user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=f"Crédito manual creado: {credit.remaining_amount} - expira {credit.expires_at or 'sin expiración'}",
        )
        return credit

    def perform_update(self, serializer):
        credit = serializer.save()
        new_status = self._compute_status(credit)
        if credit.status != new_status:
            credit.status = new_status
            credit.save(update_fields=["status"])
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=credit.user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=f"Crédito actualizado: saldo {credit.remaining_amount} / inicial {credit.initial_amount}, estado {credit.status}",
        )
        return credit


class ClientCreditViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vista de solo lectura para que los clientes consulten sus créditos/vouchers.
    """
    serializer_class = ClientCreditSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ClientCredit.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['get'], url_path='my')
    def my_credits(self, request):
        """
        Endpoint de conveniencia para compatibilidad con la estructura solicitada:
        GET /api/v1/vouchers/my/
        """
        return self.list(request)


class PaymentHistoryView(generics.ListAPIView):
    """
    Lista el historial de pagos del usuario autenticado.
    
    GET /api/finances/payments/my/
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')

