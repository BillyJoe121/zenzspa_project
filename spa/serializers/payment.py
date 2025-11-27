from decimal import Decimal

from rest_framework import serializers

from ..models import FinancialAdjustment, Payment
from users.serializers import SimpleUserSerializer
from django.contrib.auth import get_user_model

CustomUser = get_user_model()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class FinancialAdjustmentSerializer(serializers.ModelSerializer):
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
