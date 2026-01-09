"""
Views de Iniciación de Pagos.

Endpoints para iniciar flujos de pago:
- Pago de citas (appointments) - deposit/full/balance
- Suscripción VIP
- Compra de paquetes
- Creación de transacciones por método (PSE, Nequi, Daviplata, Bancolombia)
- Instituciones financieras PSE
"""
import uuid
import logging

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsVerified
from core.models import GlobalSettings
from spa.models import Appointment
from spa.serializers import PackagePurchaseCreateSerializer
from finances.models import Payment
from finances.gateway import WompiPaymentClient, build_integrity_signature
from finances.payments import PaymentService


logger = logging.getLogger(__name__)


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
    Inicia el flujo de pago para una cita.
    
    GET /api/finances/payments/appointment/<pk>/initiate/

    Query params:
    - payment_type: 'deposit' (default), 'full', o 'balance'
    - use_credits: 'true' o 'false' (default)
    - confirm: 'true' o 'false' (default) - Si debe APLICAR créditos y crear pagos
    
    Comportamiento:
    - Sin confirm=true: Retorna SOLO preview (no modifica nada)
    - Con confirm=true: Aplica créditos, crea pagos, cambia estado de cita
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request, pk):
        appointment = generics.get_object_or_404(Appointment, pk=pk, user=request.user)

        payment_type = request.query_params.get('payment_type', 'deposit')
        use_credits = request.query_params.get('use_credits', 'false').lower() == 'true'
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'

        try:
            result = PaymentService.initiate_appointment_payment(
                appointment=appointment,
                user=request.user,
                payment_type=payment_type,
                use_credits=use_credits,
                confirm=confirm
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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

        # TEMPORAL: Override redirectUrl para desarrollo local
        redirect_url = settings.WOMPI_REDIRECT_URL
        if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
            redirect_url = 'about:blank'
            logger.warning(
                f"[DEVELOPMENT] VIP: Usando 'about:blank' como redirectUrl"
            )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': redirect_url
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
        payment = PaymentService.create_package_payment(user, package)
        
        amount_in_cents = int(payment.amount * 100)
        reference = payment.transaction_id

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        # TEMPORAL: Override redirectUrl para desarrollo local
        redirect_url = settings.WOMPI_REDIRECT_URL
        if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
            redirect_url = 'about:blank'
            logger.warning(
                f"[DEVELOPMENT] Package: Usando 'about:blank' como redirectUrl"
            )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': redirect_url
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
