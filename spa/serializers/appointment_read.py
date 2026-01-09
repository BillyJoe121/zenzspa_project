from rest_framework import serializers

from ..models import Appointment
from .appointment_common import UserSummarySerializer
from .appointment_services import AppointmentItemSerializer


class AppointmentListSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    staff_member = UserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    services = AppointmentItemSerializer(source="items", many=True, read_only=True)
    total_duration_minutes = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id",
            "user",
            "services",
            "staff_member",
            "start_time",
            "end_time",
            "status",
            "status_display",
            "price_at_purchase",
            "paid_amount",
            "outstanding_balance",
            "total_duration_minutes",
            "reschedule_count",
            "available_actions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_duration_minutes(self, obj):
        return obj.total_duration_minutes

    def get_paid_amount(self, obj):
        from finances.models import Payment

        payments = obj.payments.all()
        paid = sum(p.amount for p in payments if p.status == Payment.PaymentStatus.APPROVED)
        return paid

    def get_outstanding_balance(self, obj):
        return obj.outstanding_balance

    def get_available_actions(self, obj):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return None

        user = request.user
        can_reschedule, _ = obj.can_reschedule(user)
        can_cancel, _ = obj.can_cancel(user)
        can_mark_completed, _ = obj.can_mark_completed(user)
        can_mark_no_show, _ = obj.can_mark_no_show(user)
        can_complete_final_payment, _ = obj.can_complete_final_payment(user)
        can_add_tip, _ = obj.can_add_tip(user)
        can_download_ical, _ = obj.can_download_ical(user)
        can_cancel_by_admin, _ = obj.can_cancel_by_admin(user)

        return {
            "can_reschedule": can_reschedule,
            "can_cancel": can_cancel,
            "can_mark_completed": can_mark_completed,
            "can_mark_no_show": can_mark_no_show,
            "can_complete_final_payment": can_complete_final_payment,
            "can_add_tip": can_add_tip,
            "can_download_ical": can_download_ical,
            "can_cancel_by_admin": can_cancel_by_admin,
        }


AppointmentReadSerializer = AppointmentListSerializer
AppointmentSerializer = AppointmentListSerializer
