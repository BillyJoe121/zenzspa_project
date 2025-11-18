from datetime import datetime, timedelta
from decimal import Decimal

from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from core.models import GlobalSettings
from .models import (
    ServiceCategory,
    Service,
    Package,
    StaffAvailability,
    Appointment,
    AppointmentItem,
    Payment,
    UserPackage,
    Voucher,
    PackageService,
    FinancialAdjustment,
)
from users.serializers import SimpleUserSerializer # Se mantiene tu import original
from .services import AvailabilityService

CustomUser = get_user_model()

class UserSummarySerializer(serializers.ModelSerializer):
    """
    Serializador de resumen para CustomUser.
    Expone solo la información esencial para mostrar en una cita.
    """
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name']

class ServiceSummarySerializer(serializers.ModelSerializer):
    """
    Serializador de resumen para Service.
    Expone solo la información esencial para el listado de citas.
    """
    class Meta:
        model = Service
        fields = ['id', 'name', 'duration']


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'description', 'is_low_supervision']


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description', 'duration', 'price',
            'vip_price', 'category', 'category_name', 'is_active'
        ]

class PackageServiceSerializer(serializers.ModelSerializer):
    """Serializador para el detalle de servicios en un paquete."""
    service = ServiceSerializer(read_only=True)

    class Meta:
        model = PackageService
        fields = ['service', 'quantity']

class PackageSerializer(serializers.ModelSerializer):

    services = PackageServiceSerializer(source='packageservice_set', many=True, read_only=True)

    class Meta:
        model = Package
        fields = ['id', 'name', 'description', 'price',
                  'grants_vip_months', 'is_active', 'services', 'validity_days']


class AppointmentItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los servicios incluidos en una cita."""
    service = ServiceSummarySerializer(read_only=True)

    class Meta:
        model = AppointmentItem
        fields = ['id', 'service', 'duration', 'price_at_purchase']


class AppointmentListSerializer(serializers.ModelSerializer):
    """
    Serializador CONSOLIDADO para leer (listar y detallar) citas.
    Utiliza serializadores de resumen para optimizar la respuesta y mejorar la seguridad.
    Este serializador reemplaza a los antiguos AppointmentReadSerializer y AppointmentListSerializer.
    """
    user = UserSummarySerializer(read_only=True)
    staff_member = UserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    services = AppointmentItemSerializer(source='items', many=True, read_only=True)
    total_duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id',
            'user',
            'services',
            'staff_member',
            'start_time',
            'end_time',
            'status',
            'status_display', # Campo útil para el frontend
            'price_at_purchase',
            'total_duration_minutes',
            'reschedule_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_total_duration_minutes(self, obj):
        return obj.total_duration_minutes

AppointmentReadSerializer = AppointmentListSerializer

class AppointmentCreateSerializer(serializers.Serializer):
    """
    Serializador para la creación de citas multi-servicio.
    """

    service_ids = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        many=True,
        write_only=True,
    )
    staff_member = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN]),
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
        services = data.pop('service_ids')
        if not services:
            raise serializers.ValidationError({"service_ids": "Debes seleccionar al menos un servicio."})

        staff_member = data.get('staff_member')
        requires_staff = any(not service.category.is_low_supervision for service in services)

        if requires_staff and not staff_member:
            raise serializers.ValidationError({"staff_member": "Estos servicios requieren un terapeuta asignado."})

        if not requires_staff:
            data['staff_member'] = None

        # Validar que el slot siga disponible.
        start_time = data['start_time']
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
            slot['start_time'] == normalized_start and (not staff_id or slot['staff_id'] == staff_id)
            for slot in available_slots
        )

        if not slot_is_available:
            raise serializers.ValidationError({"start_time": "El horario seleccionado ya no está disponible."})

        data['services'] = services
        return data


class TipCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


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
        fields = ['status']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class StaffAvailabilitySerializer(serializers.ModelSerializer):
    # Aquí seguimos usando tu SimpleUserSerializer para mantener la consistencia con tu código
    staff_member_details = SimpleUserSerializer(
        source='staff_member', read_only=True)
    staff_member_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN]),
        write_only=True,
        source='staff_member',
        required=False
    )

    class Meta:
        model = StaffAvailability
        fields = [
            'id', 'staff_member_details', 'staff_member_id', 'day_of_week',
            'start_time', 'end_time'
        ]

    def validate(self, data):
        if data.get('start_time') and data.get('end_time'):
            if data['start_time'] >= data['end_time']:
                raise serializers.ValidationError(
                    "La hora de inicio debe ser anterior a la hora de fin.")

        request = self.context.get('request')
        user = request.user if request else None

        if user and user.role == CustomUser.Role.ADMIN and not data.get('staff_member'):
            raise serializers.ValidationError(
                {"staff_member_id": "Un administrador debe especificar a qué miembro del personal le asigna el horario."})

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
        service_ids = data.get('service_ids')
        if service_ids and isinstance(service_ids, str):
            service_ids = [value.strip() for value in service_ids.split(',') if value.strip()]
        if not service_ids:
            single = data.get('service_id')
            if not single:
                raise serializers.ValidationError({"service_ids": "Debes proporcionar al menos un servicio."})
            service_ids = [single]
        data['service_ids'] = service_ids
        data.pop('service_id', None)
        return data

    def get_available_slots(self):
        try:
            slots = AvailabilityService.get_available_slots(
                self.validated_data['date'],
                self.validated_data['service_ids'],
                staff_member_id=self.validated_data.get('staff_member_id'),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"service_ids": str(exc)})

        return [
            {
                "start_time": slot['start_time'].isoformat(),
                "staff_id": slot['staff_id'],
                "staff_name": slot['staff_name'],
            }
            for slot in slots
        ]


class AppointmentRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField()

    def validate_new_start_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("No se puede reagendar a una fecha en el pasado.")
        return value

    def validate(self, data):
        appointment = self.context['appointment']
        new_start_time = data['new_start_time']

        if new_start_time.minute % AvailabilityService.SLOT_INTERVAL_MINUTES != 0 or new_start_time.second or new_start_time.microsecond:
            raise serializers.ValidationError(
                {"new_start_time": f"Las citas deben comenzar en intervalos de {AvailabilityService.SLOT_INTERVAL_MINUTES} minutos."}
            )

        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]:
            raise serializers.ValidationError("Solo las citas confirmadas pueden ser reagendadas.")

        service_ids = list(appointment.services.values_list('id', flat=True))
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
            slot['start_time'] == normalized_start and (not staff_id or slot['staff_id'] == staff_id)
            for slot in available_slots
        )

        if not slot_is_available:
            raise serializers.ValidationError("El nuevo horario seleccionado ya no está disponible.")

        data['new_start_time'] = normalized_start
        return data
    

class VoucherSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los Vouchers de un usuario."""
    service_name = serializers.CharField(source='service.name', read_only=True)
    is_redeemable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Voucher
        fields = [
            'id', 'code', 'service_name', 'status', 'is_redeemable', 'expires_at'
        ]

class UserPackageDetailSerializer(serializers.ModelSerializer):
    """Serializador para ver el detalle de un paquete comprado por un usuario."""
    package = PackageSerializer(read_only=True)
    vouchers = VoucherSerializer(many=True, read_only=True)

    class Meta:
        model = UserPackage
        fields = [
            'id', 'package', 'purchase_date', 'expires_at', 'vouchers'
        ]

class PackagePurchaseCreateSerializer(serializers.Serializer):
    """
    Serializador de solo escritura para iniciar la compra de un paquete.
    Espera el ID del paquete a comprar.
    """
    package_id = serializers.PrimaryKeyRelatedField(
        queryset=Package.objects.filter(is_active=True),
        source="package",
        write_only=True,
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        # La lógica de creación del pago y el UserPackage se manejará en la vista
        # Este serializador solo valida la entrada.
        return validated_data


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


class WaitlistJoinSerializer(serializers.Serializer):
    desired_date = serializers.DateField()
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_desired_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("La fecha deseada debe ser futura.")
        return value


class WaitlistConfirmSerializer(serializers.Serializer):
    accept = serializers.BooleanField(default=True)
