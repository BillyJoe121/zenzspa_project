"""
Serializers para el módulo finances.
"""
from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import CommissionLedger, Payment, FinancialAdjustment
from users.serializers import SimpleUserSerializer

CustomUser = get_user_model()


class CommissionLedgerSerializer(serializers.ModelSerializer):
    payment_id = serializers.UUIDField(source="source_payment.id", read_only=True)
    payment_type = serializers.CharField(source="source_payment.payment_type", read_only=True)
    payment_status = serializers.CharField(source="source_payment.status", read_only=True)
    payment_created_at = serializers.DateTimeField(source="source_payment.created_at", read_only=True)
    pending_amount = serializers.SerializerMethodField()

    class Meta:
        model = CommissionLedger
        fields = [
            "id",
            "amount",
             "paid_amount",
            "pending_amount",
            "status",
            "payment_id",
            "payment_type",
            "payment_status",
            "payment_created_at",
            "wompi_transfer_id",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_pending_amount(self, obj):
        return str(obj.pending_amount)


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer completo para el modelo Payment."""

    class Meta:
        model = Payment
        fields = '__all__'


class FinancialAdjustmentSerializer(serializers.ModelSerializer):
    """Serializer de lectura para FinancialAdjustment."""

    user = SimpleUserSerializer(read_only=True)
    created_by = SimpleUserSerializer(read_only=True)

    class Meta:
        model = FinancialAdjustment
        fields = [
            'id',
            'user',
            'amount',
            'adjustment_type',
            'reason',
            'related_payment',
            'created_by',
            'created_at',
        ]
        read_only_fields = fields


class FinancialAdjustmentCreateSerializer(serializers.Serializer):
    """Serializer para crear ajustes financieros."""

    user_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    adjustment_type = serializers.ChoiceField(choices=FinancialAdjustment.AdjustmentType.choices)
    reason = serializers.CharField()
    related_payment_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_user_id(self, value):
        try:
            return CustomUser.objects.get(id=value)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado.")

    def validate_related_payment_id(self, value):
        if not value:
            return None
        try:
            return Payment.objects.get(id=value)
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Pago relacionado no encontrado.")
