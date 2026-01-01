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

    # Available actions (optional, populated if request context includes user)
    available_actions = serializers.SerializerMethodField()

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
            'available_actions',
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
        """Retorna el saldo pendiente usando la propiedad del modelo."""
        return obj.outstanding_balance
    def get_available_actions(self, obj):
        """
        Returns available actions for this appointment.
        Only included if 'request' is in context and has a user.
        """
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return None

        user = request.user

        # Get all action permissions
        can_reschedule, _ = obj.can_reschedule(user)
        can_cancel, _ = obj.can_cancel(user)
        can_mark_completed, _ = obj.can_mark_completed(user)
        can_mark_no_show, _ = obj.can_mark_no_show(user)
        can_complete_final_payment, _ = obj.can_complete_final_payment(user)
        can_add_tip, _ = obj.can_add_tip(user)
        can_download_ical, _ = obj.can_download_ical(user)
        can_cancel_by_admin, _ = obj.can_cancel_by_admin(user)

        return {
            'can_reschedule': can_reschedule,
            'can_cancel': can_cancel,
            'can_mark_completed': can_mark_completed,
            'can_mark_no_show': can_mark_no_show,
            'can_complete_final_payment': can_complete_final_payment,
            'can_add_tip': can_add_tip,
            'can_download_ical': can_download_ical,
            'can_cancel_by_admin': can_cancel_by_admin,
        }



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
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            raise serializers.ValidationError("Solo las citas confirmadas, reagendadas o totalmente pagadas pueden ser reagendadas.")

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
        max_length=1,
        help_text="ID del servicio a agendar (solo 1 servicio por cita)."
    )
    staff_member_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID del staff asignado (opcional para servicios de baja supervisión)."
    )
    start_time = serializers.DateTimeField(
        help_text="Fecha y hora de inicio de la cita."
    )
    payment_method = serializers.ChoiceField(
        choices=['VOUCHER', 'CREDIT', 'PAYMENT_LINK', 'CASH'],
        default='PAYMENT_LINK',
        help_text="Método de pago: VOUCHER (usar voucher), CREDIT (usar crédito), PAYMENT_LINK (generar link Wompi), CASH (pago en efectivo)"
    )
    voucher_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID del voucher a usar (requerido si payment_method=VOUCHER)"
    )
    cash_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Monto pagado en efectivo (requerido si payment_method=CASH)"
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
        """Valida disponibilidad, servicios y método de pago."""
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
        
        # Validar método de pago
        payment_method = data.get('payment_method', 'PAYMENT_LINK')
        voucher_id = data.get('voucher_id')
        
        if payment_method == 'VOUCHER':
            if not voucher_id:
                raise serializers.ValidationError(
                    {"voucher_id": "Se requiere un voucher_id cuando payment_method es VOUCHER."}
                )
            
            # Validar que el voucher existe y está disponible
            from ..models import Voucher
            try:
                voucher = Voucher.objects.get(
                    id=voucher_id,
                    user_id=data['client_id'],
                    status=Voucher.VoucherStatus.AVAILABLE,
                )
            except Voucher.DoesNotExist:
                raise serializers.ValidationError(
                    {"voucher_id": "Voucher no encontrado, no disponible o no pertenece al cliente."}
                )
            
            # Validar que el voucher no esté expirado
            if voucher.expires_at and voucher.expires_at < timezone.now().date():
                raise serializers.ValidationError(
                    {"voucher_id": "El voucher ha expirado."}
                )
            
            # Validar que el voucher sea para uno de los servicios solicitados
            if voucher.service_id not in service_ids:
                raise serializers.ValidationError(
                    {"voucher_id": f"El voucher es para '{voucher.service.name}', no para los servicios seleccionados."}
                )
            
            # Si hay múltiples servicios, solo uno puede ser cubierto por el voucher
            if len(service_ids) > 1:
                # Esto está permitido, pero solo un servicio será cubierto por el voucher
                pass
            
            data['voucher'] = voucher
        
        # Validar cash_amount si payment_method es CASH
        if payment_method == 'CASH':
            cash_amount = data.get('cash_amount')
            if not cash_amount or cash_amount <= 0:
                raise serializers.ValidationError(
                    {"cash_amount": "El monto en efectivo es requerido y debe ser mayor a 0 cuando payment_method es CASH."}
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

