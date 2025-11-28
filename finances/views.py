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

from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin, IsVerified
from core.models import GlobalSettings
from spa.models import Appointment
from .services import DeveloperCommissionService, WompiDisbursementClient
from .models import CommissionLedger, Payment, WebhookEvent
from .serializers import CommissionLedgerSerializer
from .gateway import WompiPaymentClient, build_integrity_signature
from .webhooks import WompiWebhookService
from spa.serializers import PackagePurchaseCreateSerializer


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
            institutions_data, status_code = client.get_pse_financial_institutions()

            if status_code == 200:
                return Response(institutions_data, status=200)
            else:
                return Response(
                    {"error": "No se pudieron obtener los bancos PSE"},
                    status=status_code
                )
        except Exception as e:
            return Response(
                {"error": f"Error al consultar bancos PSE: {str(e)}"},
                status=500
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

        try:
            payment = appointment.payments.get(status=Payment.PaymentStatus.PENDING)
        except Payment.DoesNotExist:
             return Response(
                {"error": "No se encontró un registro de pago pendiente para esta cita."},
                status=status.HTTP_404_NOT_FOUND
            )

        amount_in_cents = int(payment.amount * 100)
        reference = f"APPOINTMENT-{appointment.id}-PAYMENT-{payment.id}"
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
            'signature:integrity': signature,
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
        webhook_service = WompiWebhookService(request.data, headers=request.headers)
        event_type = webhook_service.event_type

        try:
            if event_type == "transaction.updated":
                result = webhook_service.process_transaction_update()
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
            'signature:integrity': signature,
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
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)
