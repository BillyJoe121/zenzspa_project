from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.models import GlobalSettings
from ..models import (
    Appointment,
    AppointmentItem,
    Service,
    ServiceCategory,
    StaffAvailability,
)
from ..services import AvailabilityService
from users.serializers import SimpleUserSerializer

CustomUser = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name']


class ServiceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'duration']


class ServiceCategorySerializer(serializers.ModelSerializer):
    service_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'description', 'is_low_supervision', 'service_count']
        read_only_fields = ['service_count']

    def get_service_count(self, obj):
        """Cuenta servicios activos en esta categoría."""
        return obj.services.filter(is_active=True, deleted_at__isnull=True).count()


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description', 'duration', 'price',
            'vip_price', 'category', 'category_name', 'is_active',
            'what_is_included', 'benefits', 'contraindications'
        ]


class AppointmentItemSerializer(serializers.ModelSerializer):
    service = ServiceSummarySerializer(read_only=True)

    class Meta:
        model = AppointmentItem
        fields = ['id', 'service', 'duration', 'price_at_purchase']


class AppointmentListSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    staff_member = UserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    services = AppointmentItemSerializer(source='items', many=True, read_only=True)
    total_duration_minutes = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

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
            'status_display',
            'price_at_purchase',
            'paid_amount',
            'outstanding_balance',
            'total_duration_minutes',
            'reschedule_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_total_duration_minutes(self, obj):
        return obj.total_duration_minutes

    def get_paid_amount(self, obj):
        """Calcula el monto total pagado (solo pagos aprobados)."""
        # Importación local para evitar ciclos
        from finances.models import Payment
        payments = obj.payments.all()
        paid = sum(p.amount for p in payments if p.status == Payment.PaymentStatus.APPROVED)
        return paid

    def get_outstanding_balance(self, obj):
        """Calcula el saldo pendiente."""
        paid = self.get_paid_amount(obj)
        return max(obj.price_at_purchase - paid, Decimal('0.00'))


AppointmentReadSerializer = AppointmentListSerializer
AppointmentSerializer = AppointmentListSerializer


class AppointmentCreateSerializer(serializers.Serializer):
    service_ids = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        many=True,
        write_only=True,
    )
    staff_member = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True  # ✅ Solo permitir staff activos
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
        services = data.pop('service_ids')
        if not services:
            raise serializers.ValidationError({"service_ids": "Debes seleccionar al menos un servicio."})

        staff_member = data.get('staff_member')
        requires_staff = any(not service.category.is_low_supervision for service in services)

        if requires_staff and not staff_member:
            raise serializers.ValidationError({"staff_member": "Estos servicios requieren un terapeuta asignado."})

        if not requires_staff:
            data['staff_member'] = None

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


class StaffAvailabilitySerializer(serializers.ModelSerializer):
    staff_member_details = SimpleUserSerializer(source='staff_member', read_only=True)
    staff_member_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(
            role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
            is_active=True  # ✅ Solo permitir staff activos
        ),
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
                "staff_label": slot['staff_label'],
            }
            for slot in slots
        ]


class AppointmentRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField()
    skip_counter = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Si es True, no incrementa el contador de reagendamientos del cliente. Solo para Admin/Staff."
    )

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


class AdminAppointmentCreateSerializer(serializers.Serializer):
    """
    Serializer para que admin/staff cree citas en nombre de un cliente.
    
    Usado en: POST /api/appointments/admin-create/
    """
    client_id = serializers.UUIDField(
        help_text="UUID del cliente para quien se crea la cita."
    )
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        help_text="IDs de los servicios a agendar."
    )
    staff_member_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID del staff asignado (opcional para servicios de baja supervisión)."
    )
    start_time = serializers.DateTimeField(
        help_text="Fecha y hora de inicio de la cita."
    )
    send_whatsapp = serializers.BooleanField(
        default=True,
        help_text="Si enviar notificación WhatsApp con link de pago."
    )

    def validate_client_id(self, value):
        """Valida que el cliente exista y esté activo."""
        try:
            client = CustomUser.objects.get(
                id=value,
                role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
                is_active=True,
                is_persona_non_grata=False,
            )
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(
                "Cliente no encontrado, inactivo o bloqueado."
            )
        return value

    def validate_start_time(self, value):
        """Valida que la hora de inicio sea futura y en intervalo válido."""
        if value < timezone.now():
            raise serializers.ValidationError("La cita no puede programarse en el pasado.")
        if value.minute % AvailabilityService.SLOT_INTERVAL_MINUTES != 0:
            raise serializers.ValidationError(
                f"Las citas deben comenzar en intervalos de {AvailabilityService.SLOT_INTERVAL_MINUTES} minutos."
            )
        return value.replace(second=0, microsecond=0)

    def validate(self, data):
        """Valida disponibilidad y servicios."""
        # Obtener servicios
        service_ids = data['service_ids']
        services = Service.objects.filter(id__in=service_ids, is_active=True)
        if services.count() != len(service_ids):
            raise serializers.ValidationError(
                {"service_ids": "Algunos servicios no existen o están inactivos."}
            )
        
        # Verificar si requiere staff
        requires_staff = any(not s.category.is_low_supervision for s in services)
        staff_member_id = data.get('staff_member_id')
        
        if requires_staff and not staff_member_id:
            raise serializers.ValidationError(
                {"staff_member_id": "Estos servicios requieren un terapeuta asignado."}
            )
        
        # Validar staff si se proporcionó
        staff_member = None
        if staff_member_id:
            try:
                staff_member = CustomUser.objects.get(
                    id=staff_member_id,
                    role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
                    is_active=True,
                )
            except CustomUser.DoesNotExist:
                raise serializers.ValidationError(
                    {"staff_member_id": "Staff no encontrado o inactivo."}
                )
        
        # Verificar disponibilidad
        start_time = data['start_time']
        try:
            available_slots = AvailabilityService.get_available_slots(
                start_time.date(),
                service_ids,
                staff_member_id=staff_member_id,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"service_ids": str(exc)})
        
        slot_is_available = any(
            slot['start_time'] == start_time and 
            (not staff_member_id or slot['staff_id'] == staff_member_id)
            for slot in available_slots
        )
        
        if not slot_is_available:
            raise serializers.ValidationError(
                {"start_time": "El horario seleccionado ya no está disponible."}
            )
        
        data['services'] = list(services)
        data['staff_member'] = staff_member
        return data


class ReceiveAdvanceInPersonSerializer(serializers.Serializer):
    """
    Serializer para registrar anticipo recibido en persona.
    
    Usado en: POST /api/appointments/{id}/receive-advance-in-person/
    """
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
        help_text="Monto recibido en persona (puede ser menor al anticipo requerido)."
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Notas opcionales sobre el pago."
    )

