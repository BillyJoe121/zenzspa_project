from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from ..models import Service
from ..services import AvailabilityService
from .appointment_common import CustomUser


class AdminAppointmentCreateSerializer(serializers.Serializer):
    """
    Serializer para que admin/staff cree citas en nombre de un cliente.
    """

    client_id = serializers.UUIDField(help_text="UUID del cliente para quien se crea la cita.")
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=1,
        help_text="ID del servicio a agendar (solo 1 servicio por cita).",
    )
    staff_member_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID del staff asignado (opcional para servicios de baja supervisión).",
    )
    start_time = serializers.DateTimeField(help_text="Fecha y hora de inicio de la cita.")
    payment_method = serializers.ChoiceField(
        choices=["VOUCHER", "CREDIT", "PAYMENT_LINK", "CASH"],
        default="PAYMENT_LINK",
        help_text="Método de pago: VOUCHER (usar voucher), CREDIT (usar crédito), PAYMENT_LINK (generar link Wompi), CASH (pago en efectivo)",
    )
    voucher_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID del voucher a usar (requerido si payment_method=VOUCHER)",
    )
    cash_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Monto pagado en efectivo (requerido si payment_method=CASH)",
    )
    send_whatsapp = serializers.BooleanField(
        default=True,
        help_text="Si enviar notificación WhatsApp con link de pago.",
    )

    def validate_client_id(self, value):
        try:
            CustomUser.objects.get(
                id=value,
                role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
                is_active=True,
                is_persona_non_grata=False,
            )
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Cliente no encontrado, inactivo o bloqueado.")
        return value

    def validate_start_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("La cita no puede programarse en el pasado.")
        if value.minute % AvailabilityService.SLOT_INTERVAL_MINUTES != 0:
            raise serializers.ValidationError(
                f"Las citas deben comenzar en intervalos de {AvailabilityService.SLOT_INTERVAL_MINUTES} minutos."
            )
        return value.replace(second=0, microsecond=0)

    def validate(self, data):
        service_ids = data["service_ids"]
        services = Service.objects.filter(id__in=service_ids, is_active=True)
        if services.count() != len(service_ids):
            raise serializers.ValidationError({"service_ids": "Algunos servicios no existen o están inactivos."})

        requires_staff = any(not s.category.is_low_supervision for s in services)
        staff_member_id = data.get("staff_member_id")

        if requires_staff and not staff_member_id:
            raise serializers.ValidationError({"staff_member_id": "Estos servicios requieren un terapeuta asignado."})

        staff_member = None
        if staff_member_id:
            try:
                staff_member = CustomUser.objects.get(
                    id=staff_member_id,
                    role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
                    is_active=True,
                )
            except CustomUser.DoesNotExist:
                raise serializers.ValidationError({"staff_member_id": "Staff no encontrado o inactivo."})

        start_time = data["start_time"]
        try:
            available_slots = AvailabilityService.get_available_slots(
                start_time.date(),
                service_ids,
                staff_member_id=staff_member_id,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"service_ids": str(exc)})

        slot_is_available = any(
            slot["start_time"] == start_time and (not staff_member_id or slot["staff_id"] == staff_member_id)
            for slot in available_slots
        )

        if not slot_is_available:
            raise serializers.ValidationError({"start_time": "El horario seleccionado ya no está disponible."})

        payment_method = data.get("payment_method", "PAYMENT_LINK")
        voucher_id = data.get("voucher_id")

        if payment_method == "VOUCHER":
            if not voucher_id:
                raise serializers.ValidationError(
                    {"voucher_id": "Se requiere un voucher_id cuando payment_method es VOUCHER."}
                )

            from ..models import Voucher

            try:
                voucher = Voucher.objects.get(
                    id=voucher_id,
                    user_id=data["client_id"],
                    status=Voucher.VoucherStatus.AVAILABLE,
                )
            except Voucher.DoesNotExist:
                raise serializers.ValidationError(
                    {"voucher_id": "Voucher no encontrado, no disponible o no pertenece al cliente."}
                )

            if voucher.expires_at and voucher.expires_at < timezone.now().date():
                raise serializers.ValidationError({"voucher_id": "El voucher ha expirado."})

            if voucher.service_id not in service_ids:
                raise serializers.ValidationError(
                    {"voucher_id": f"El voucher es para '{voucher.service.name}', no para los servicios seleccionados."}
                )

            data["voucher"] = voucher

        if payment_method == "CASH":
            cash_amount = data.get("cash_amount")
            if not cash_amount or cash_amount <= 0:
                raise serializers.ValidationError(
                    {"cash_amount": "El monto en efectivo es requerido y debe ser mayor a 0 cuando payment_method es CASH."}
                )

        data["services"] = list(services)
        data["staff_member"] = staff_member
        return data


class ReceiveAdvanceInPersonSerializer(serializers.Serializer):
    """
    Serializer para registrar anticipo recibido en persona.
    """

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Monto recibido en persona (puede ser menor al anticipo requerido).",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Notas opcionales sobre el pago.",
    )
