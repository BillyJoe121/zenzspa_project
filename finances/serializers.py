"""
Serializers para el módulo finances.
"""
from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import ClientCredit, CommissionLedger, Payment, FinancialAdjustment
from .models import ClientCredit, CommissionLedger, Payment, FinancialAdjustment
from users.serializers import SimpleUserSerializer
from spa.serializers.appointment import AppointmentListSerializer

CustomUser = get_user_model()


class CommissionLedgerSerializer(serializers.ModelSerializer):
    payment_id = serializers.UUIDField(source="source_payment.id", read_only=True)
    payment_type = serializers.CharField(source="source_payment.payment_type", read_only=True)
    payment_status = serializers.CharField(source="source_payment.status", read_only=True)
    payment_created_at = serializers.DateTimeField(source="source_payment.created_at", read_only=True)
    client_name = serializers.CharField(source="source_payment.user.get_full_name", read_only=True, default="Cliente no identificado")
    client_email = serializers.EmailField(source="source_payment.user.email", read_only=True, default="")
    payment_amount = serializers.DecimalField(source="source_payment.amount", max_digits=12, decimal_places=2, read_only=True)
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
            "payment_amount",
            "client_name",
            "client_email",
            "wompi_transfer_id",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_pending_amount(self, obj):
        return str(obj.pending_amount)


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer completo para el modelo Payment."""

    appointment = AppointmentListSerializer(read_only=True)

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


class ClientCreditAdminSerializer(serializers.ModelSerializer):
    """
    Serializador de administración para gestionar créditos de clientes.
    Permite crear, editar y ajustar expiración/estado.
    """
    user = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    user_data = SimpleUserSerializer(source='user', read_only=True)

    class Meta:
        model = ClientCredit
        fields = [
            "id",
            "user",
            "user_data",
            "originating_payment",
            "initial_amount",
            "remaining_amount",
            "status",
            "expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {
            "remaining_amount": {"required": False},
        }

    def validate(self, attrs):
        initial = attrs.get("initial_amount", getattr(self.instance, "initial_amount", None))
        remaining = attrs.get("remaining_amount", getattr(self.instance, "remaining_amount", None))

        if initial is None or remaining is None:
            return attrs

        if remaining < 0:
            raise serializers.ValidationError({"remaining_amount": "El saldo restante no puede ser negativo."})
        if remaining > initial:
            raise serializers.ValidationError({"remaining_amount": "El saldo restante no puede superar el monto inicial."})
        return attrs

    def create(self, validated_data):
        # Si no se especifica remaining_amount, asumir el total inicial.
        if validated_data.get("remaining_amount") is None:
            validated_data["remaining_amount"] = validated_data["initial_amount"]
        # Estado se setea automáticamente según remaining_amount en el ViewSet.
        return super().create(validated_data)


class ClientCreditSerializer(serializers.ModelSerializer):
    """Serializer para visualización de créditos por parte del cliente."""
    class Meta:
        model = ClientCredit
        fields = [
            "id",
            "initial_amount",
            "remaining_amount",
            "status",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields
