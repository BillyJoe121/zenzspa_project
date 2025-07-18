from rest_framework import serializers
from django.utils import timezone
from .models import ServiceCategory, Service, Package, StaffAvailability, Appointment, Payment
from users.serializers import SimpleUserSerializer
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from core.models import GlobalSettings
from decimal import Decimal
from .services import calculate_available_slots

CustomUser = get_user_model()


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

class PackageSerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)

    class Meta:
        model = Package
        fields = ['id', 'name', 'description', 'price',
                  'grants_vip_months', 'is_active', 'services']


class AppointmentReadSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    staff_member = SimpleUserSerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = '__all__'

class AppointmentCreateSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    advance_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'user', 'service', 'staff_member', 'start_time',
            'status', 'price_at_purchase', 'end_time',
            'advance_amount'
        ]
        read_only_fields = ['status', 'price_at_purchase', 'end_time', 'advance_amount']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        service_id = self.context['request'].data.get('service')
        if service_id:
            try:
                service = Service.objects.get(id=service_id)
                if service.category.is_low_supervision:
                    self.fields['staff_member'].required = False
            except Service.DoesNotExist:
                pass

    def validate(self, data):
        service = data['service']
        start_time = data['start_time']
        user = data['user']

        if Appointment.objects.filter(
            user=user,
            status=Appointment.AppointmentStatus.COMPLETED_PENDING_FINAL_PAYMENT
        ).exists():
            raise serializers.ValidationError(
                "No puedes agendar una nueva cita porque tienes un pago final pendiente. Por favor, completa el pago de tu cita anterior."
            )

        if start_time < timezone.now():
            raise serializers.ValidationError("No se puede reservar una cita en el pasado.")

        # La validación de disponibilidad ahora se delega al servicio centralizado
        available_slots = calculate_available_slots(service.id, start_time.date())
        requested_time_str = start_time.strftime('%H:%M')

        if requested_time_str not in available_slots:
            raise serializers.ValidationError("El horario seleccionado ya no está disponible.")

        if not service.category.is_low_supervision:
            staff_member = data.get('staff_member')
            if not staff_member:
                raise serializers.ValidationError({"staff_member": "Este servicio requiere seleccionar un miembro del personal."})

            staff_is_available = any(
                slot['staff_id'] == staff_member.id
                for slot in available_slots[requested_time_str]
            )
            if not staff_is_available:
                raise serializers.ValidationError("El miembro del personal seleccionado ya no está disponible en este horario.")
        else:
            data['staff_member'] = None

        active_appointments = Appointment.objects.filter(
            user=user,
            status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PENDING_ADVANCE]
        ).count()

        if user.role == CustomUser.Role.CLIENT and active_appointments >= 1:
            raise serializers.ValidationError("Como CLIENTE, solo puedes tener 1 cita activa.")
        if user.role == CustomUser.Role.VIP and active_appointments >= 4:
            raise serializers.ValidationError("Como VIP, puedes tener hasta 4 citas activas.")

        return data

    def create(self, validated_data):
        service = validated_data['service']
        user = validated_data['user']
        
        settings = GlobalSettings.load()
        
        price = service.vip_price if user.role == CustomUser.Role.VIP and service.vip_price is not None else service.price
        validated_data['price_at_purchase'] = price
        
        advance_percentage = Decimal(settings.advance_payment_percentage / 100)
        advance_amount = price * advance_percentage
        
        self.advance_amount = advance_amount
        
        validated_data['status'] = Appointment.AppointmentStatus.PENDING_ADVANCE
        
        validated_data['end_time'] = validated_data['start_time'] + timedelta(minutes=service.duration)
        
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if hasattr(self, 'advance_amount'):
            representation['advance_amount'] = self.advance_amount
        return representation
    
class AppointmentStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['status']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'


class StaffAvailabilitySerializer(serializers.ModelSerializer):
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

        # Si el usuario es ADMIN, es obligatorio que especifique a quién le está creando el horario.
        if user and user.role == CustomUser.Role.ADMIN and not data.get('staff_member'):
            raise serializers.ValidationError(
                {"staff_member_id": "Un administrador debe especificar a qué miembro del personal le asigna el horario."})

        return data


class AvailabilityCheckSerializer(serializers.Serializer):
    service_id = serializers.UUIDField()
    date = serializers.DateField()

    def get_available_slots(self):
        service_id = self.validated_data['service_id']
        selected_date = self.validated_data['date']

        try:
            service = Service.objects.get(id=service_id, is_active=True)
        except Service.DoesNotExist:
            raise serializers.ValidationError({"service_id": "El servicio no existe o no está activo."})

        # --- INICIO DE LA MODIFICACIÓN ---
        # 1. Cargar la configuración global que contiene el tiempo de búfer
        settings = GlobalSettings.load()
        buffer_time = timedelta(minutes=settings.appointment_buffer_time)
        service_duration = timedelta(minutes=service.duration)
        
        # 2. Obtener todas las citas activas para la fecha seleccionada
        day_of_week = selected_date.isoweekday()
        all_availabilities = StaffAvailability.objects.filter(day_of_week=day_of_week).select_related('staff_member')
        booked_appointments = Appointment.objects.filter(
            start_time__date=selected_date,
            status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PENDING_ADVANCE]
        )
        # --- FIN DE LA MODIFICACIÓN ---

        slots = {}
        for availability in all_availabilities:
            staff = availability.staff_member

            slot_time = datetime.combine(selected_date, availability.start_time)
            schedule_end_time = datetime.combine(selected_date, availability.end_time)

            while slot_time + service_duration <= schedule_end_time:
                slot_end = slot_time + service_duration

                # --- INICIO DE LA MODIFICACIÓN ---
                # 3. Comprobar conflictos considerando el tiempo de búfer
                is_booked = booked_appointments.filter(
                    staff_member=staff,
                    # Un slot está ocupado si una nueva cita (slot_time) empieza antes
                    # de que una cita existente (end_time) MÁS su búfer de limpieza terminen.
                    start_time__lt=slot_end + buffer_time,
                    # Y si la nueva cita termina (slot_end) después de que una cita existente (start_time)
                    # MENOS el búfer de limpieza comience.
                    end_time__gt=slot_time - buffer_time
                ).exists()
                # --- FIN DE LA MODIFICACIÓN ---

                if not is_booked:
                    time_str = slot_time.strftime('%H:%M')
                    if time_str not in slots:
                        slots[time_str] = []
                    
                    slots[time_str].append({
                        "staff_id": staff.id,
                        "staff_name": f"{staff.first_name} {staff.last_name}"
                    })
                
                # Avanzar al siguiente posible slot
                slot_time += timedelta(minutes=15) # Asumimos incrementos de 15 minutos

        sorted_slots = dict(sorted(slots.items()))
        return sorted_slots

class AppointmentRescheduleSerializer(serializers.Serializer):
    new_start_time = serializers.DateTimeField()

    def validate_new_start_time(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("No se puede reagendar a una fecha en el pasado.")
        return value

    def validate(self, data):
        appointment = self.context['appointment']
        new_start_time = data['new_start_time']

        if appointment.status != Appointment.AppointmentStatus.CONFIRMED:
            raise serializers.ValidationError("Solo las citas confirmadas (con anticipo pagado) pueden ser reagendadas.")

        if appointment.reschedule_count >= 2:
            raise serializers.ValidationError("Esta cita ya ha sido reagendada el número máximo de veces (2).")

        if appointment.start_time - timezone.now() < timedelta(hours=24):
            raise serializers.ValidationError("Las citas solo pueden ser reagendadas con más de 24 horas de antelación.")

        # Se reutiliza el servicio de cálculo de disponibilidad
        available_slots = calculate_available_slots(appointment.service.id, new_start_time.date())
        requested_time_str = new_start_time.strftime('%H:%M')

        if requested_time_str not in available_slots:
            raise serializers.ValidationError("El nuevo horario seleccionado ya no está disponible.")

        staff_is_available = any(
            slot['staff_id'] == appointment.staff_member.id
            for slot in available_slots[requested_time_str]
        )
        if not staff_is_available:
            raise serializers.ValidationError("El miembro del personal ya no está disponible en el nuevo horario.")

        return data

    def save(self, **kwargs):
        appointment = self.context['appointment']
        new_start_time = self.validated_data['new_start_time']

        appointment.start_time = new_start_time
        appointment.end_time = new_start_time + timedelta(minutes=appointment.service.duration)
        appointment.reschedule_count += 1
        appointment.save(
            update_fields=['start_time', 'end_time', 'reschedule_count', 'updated_at'])

        return appointment

class AppointmentListSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name')
    staff_name = serializers.CharField(source='staff_member.get_full_name')
    user_name = serializers.CharField(source='user.get_full_name')

    class Meta:
        model = Appointment
        fields = [
            'id', 'user', 'user_name', 'service_name', 'staff_name',
            'start_time', 'end_time', 'status', 'price_at_purchase',
            'reschedule_count', 'created_at'
        ]
