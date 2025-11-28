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
    FinancialAdjustmentSerializer,
    FinancialAdjustmentCreateSerializer,
)
from finances.services import FinancialAdjustmentService
from finances.payments import PaymentService
from finances.webhooks import WompiWebhookService
from finances.gateway import build_integrity_signature
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
