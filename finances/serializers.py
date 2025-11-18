from rest_framework import serializers

from .models import CommissionLedger


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
