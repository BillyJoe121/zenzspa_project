from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from ..models import Appointment, Service
from ..services import AvailabilityService
from .appointment_common import CustomUser


class AppointmentCreateSerializer(serializers.Serializer):
    service_ids = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        many=True,
        write_only=True,
    )
    staff_member = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True,
        ),
        required=False,
        allow_null=True,
    )
    start_time = serializers.DateTimeField()

    def validate_start_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("La cita no puede programarse en el pasado.")
        if value.minute % AvailabilityService.SLOT_INTERVAL_MINUTES != 0 or value.second or value.microsecond:
            raise serializers.ValidationError(
                f"Las citas deben comenzar en intervalos de {AvailabilityService.SLOT_INTERVAL_MINUTES} minutos."
            )
        return value

    def validate(self, data):
        services = data.pop("service_ids")
        if not services:
            raise serializers.ValidationError({"service_ids": "Debes seleccionar al menos un servicio."})

        staff_member = data.get("staff_member")
        requires_staff = any(not service.category.is_low_supervision for service in services)

        if requires_staff and not staff_member:
            raise serializers.ValidationError({"staff_member": "Estos servicios requieren un terapeuta asignado."})

        if not requires_staff:
            data["staff_member"] = None

        start_time = data["start_time"]
        normalized_start = start_time.replace(second=0, microsecond=0)
        service_ids = [service.id for service in services]
        staff_id = staff_member.id if staff_member else None

        try:
            available_slots = AvailabilityService.get_available_slots(
                normalized_start.date(),
                service_ids,
                staff_member_id=staff_id,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"service_ids": str(exc)})

        slot_is_available = any(
            slot["start_time"] == normalized_start and (not staff_id or slot["staff_id"] == staff_id)
            for slot in available_slots
        )

        if not slot_is_available:
            raise serializers.ValidationError({"start_time": "El horario seleccionado ya no está disponible."})

        data["services"] = services
        return data


class TipCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))


class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Motivo opcional de la cancelación.",
    )


class AppointmentStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["status"]
