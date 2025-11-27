import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from core.models import GlobalSettings
from users.permissions import IsVerified, IsAdminUser
from ..models import (
    Appointment,
    Payment,
    Package,
    UserPackage,
    Voucher,
    WebhookEvent,
)
from ..serializers import (
    AppointmentReadSerializer,
    PackagePurchaseCreateSerializer,
    UserPackageDetailSerializer,
    VoucherSerializer,
    FinancialAdjustmentCreateSerializer,
    FinancialAdjustmentSerializer,
)
from ..services import PaymentService, WompiWebhookService, FinancialAdjustmentService
from .appointments import AppointmentViewSet  # for compatibility re-export


class UserPackageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserPackageDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserPackage.objects.filter(user=self.request.user).select_related('package').prefetch_related('vouchers__service')


class VoucherViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VoucherSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Voucher.objects.filter(user=self.request.user).select_related('service', 'user_package')


class InitiatePackagePurchaseView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = PackagePurchaseCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        package = serializer.validated_data['package']
        user = request.user

        reference = f"PACKAGE-{package.id}-{uuid.uuid4().hex[:8]}"
        amount_in_cents = int(package.price * 100)

        Payment.objects.create(
            user=user,
            amount=package.price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.PACKAGE,
            transaction_id=reference
        )

        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class InitiateAppointmentPaymentView(generics.GenericAPIView):
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
        
        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()
        
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

        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class CancelVipSubscriptionView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsVerified]

    def post(self, request, *args, **kwargs):
        user = request.user
        user.vip_auto_renew = False
        user.save(update_fields=['vip_auto_renew', 'updated_at'])
        return Response({"detail": "La renovación automática ha sido desactivada."}, status=status.HTTP_200_OK)


class FinancialAdjustmentView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = FinancialAdjustmentCreateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user_id']
        amount = serializer.validated_data['amount']
        adjustment_type = serializer.validated_data['adjustment_type']
        reason = serializer.validated_data['reason']
        related_payment = serializer.validated_data.get('related_payment_id')

        adjustment = FinancialAdjustmentService.create_adjustment(
            user=user,
            amount=amount,
            adjustment_type=adjustment_type,
            reason=reason,
            created_by=request.user,
            related_payment=related_payment,
        )
        output = FinancialAdjustmentSerializer(adjustment, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)
