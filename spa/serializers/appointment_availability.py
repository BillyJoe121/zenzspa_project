from django.utils import timezone
from rest_framework import serializers

from ..models import Appointment, StaffAvailability
from ..services import AvailabilityService
from .appointment_common import CustomUser


class StaffAvailabilitySerializer(serializers.ModelSerializer):
    staff_member_details = serializers.SerializerMethodField()
    staff_member_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True,
        ),
        write_only=True,
        source="staff_member",
        required=False,
    )

    class Meta:
        model = StaffAvailability
        fields = [
            "id",
            "staff_member_details",
            "staff_member_id",
            "day_of_week",
            "start_time",
            "end_time",
        ]

    def get_staff_member_details(self, obj):
        from users.serializers import SimpleUserSerializer

        return SimpleUserSerializer(obj.staff_member).data

    def validate(self, data):
        if data.get("start_time") and data.get("end_time"):
            if data["start_time"] >= data["end_time"]:
                raise serializers.ValidationError("La hora de inicio debe ser anterior a la hora de fin.")

        request = self.context.get("request")
        user = request.user if request else None

        if user and user.role == CustomUser.Role.ADMIN and not data.get("staff_member"):
            raise serializers.ValidationError(
                {"staff_member_id": "Un administrador debe especificar a qué miembro del personal le asigna el horario."}
            )

        return data


class AvailabilityCheckSerializer(serializers.Serializer):
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=False,
    )
    service_id = serializers.UUIDField(required=False)
    date = serializers.DateField()
    staff_member_id = serializers.UUIDField(required=False)

    def validate(self, data):
        service_ids = data.get("service_ids")
        if service_ids and isinstance(service_ids, str):
            service_ids = [value.strip() for value in service_ids.split(",") if value.strip()]
        if not service_ids:
            single = data.get("service_id")
            if not single:
                raise serializers.ValidationError({"service_ids": "Debes proporcionar al menos un servicio."})
            service_ids = [single]
        data["service_ids"] = service_ids
        data.pop("service_id", None)
        return data

    def get_available_slots(self):
        try:
            slots = AvailabilityService.get_available_slots(
                self.validated_data["date"],
                self.validated_data["service_ids"],
                staff_member_id=self.validated_data.get("staff_member_id"),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"service_ids": str(exc)})

        return [
            {
                "start_time": slot["start_time"].isoformat(),
                "staff_id": slot["staff_id"],
                "staff_label": slot["staff_label"],
            }
            for slot in slots
        ]


class AppointmentRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField()
    skip_counter = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Si es True, no incrementa el contador de reagendamientos del cliente. Solo para Admin/Staff.",
    )

    def validate_new_start_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("No se puede reagendar a una fecha en el pasado.")
        return value

    def validate(self, data):
        appointment = self.context["appointment"]
        new_start_time = data["new_start_time"]

        if new_start_time.minute % AvailabilityService.SLOT_INTERVAL_MINUTES != 0 or new_start_time.second or new_start_time.microsecond:
            raise serializers.ValidationError(
                {"new_start_time": f"Las citas deben comenzar en intervalos de {AvailabilityService.SLOT_INTERVAL_MINUTES} minutos."}
            )

        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            raise serializers.ValidationError("Solo las citas confirmadas, reagendadas o totalmente pagadas pueden ser reagendadas.")

        service_ids = list(appointment.services.values_list("id", flat=True))
        if not service_ids:
            raise serializers.ValidationError("La cita no tiene servicios asociados para reagendar.")

        staff_id = appointment.staff_member_id
        normalized_start = new_start_time.replace(second=0, microsecond=0)

        try:
            available_slots = AvailabilityService.get_available_slots(
                normalized_start.date(),
                service_ids,
                staff_member_id=staff_id,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"new_start_time": str(exc)})

        slot_is_available = any(
            slot["start_time"] == normalized_start and (not staff_id or slot["staff_id"] == staff_id)
            for slot in available_slots
        )

        if not slot_is_available:
            raise serializers.ValidationError("El nuevo horario seleccionado ya no está disponible.")

        data["new_start_time"] = normalized_start
        return data


class WaitlistJoinSerializer(serializers.Serializer):
    """Serializer para unirse a la lista de espera."""

    desired_date = serializers.DateField()
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class WaitlistConfirmSerializer(serializers.Serializer):
    """Serializer para confirmar/rechazar oferta de lista de espera."""

    accept = serializers.BooleanField()
