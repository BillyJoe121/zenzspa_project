from rest_framework import serializers
from django.utils import timezone
from .models import ServiceCategory, Service, Package, StaffAvailability, Appointment, Payment
from users.serializers import SimpleUserSerializer
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta

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

    class Meta:
        model = Appointment
        fields = [
            'id', 'user', 'service', 'staff_member', 'start_time',
            'status', 'price_at_purchase', 'end_time'
        ]
        read_only_fields = ['status', 'price_at_purchase', 'end_time']

    def validate(self, data):
        service = data['service']
        staff_member = data['staff_member']
        start_time = data['start_time']
        end_time = start_time + timedelta(minutes=service.duration)
        user = data['user']

        # Rule: Prevent booking in the past
        if start_time < timezone.now():
            raise serializers.ValidationError(
                "Cannot book an appointment in the past.")

        # Rule: Check staff availability
        day_of_week = start_time.isoweekday()
        if not StaffAvailability.objects.filter(
            staff_member=staff_member,
            day_of_week=day_of_week,
            start_time__lte=start_time.time(),
            end_time__gte=end_time.time()
        ).exists():
            raise serializers.ValidationError(
                "The staff member is not available at the selected time.")

        # Rule: Check for conflicting appointments for the staff member
        if Appointment.objects.filter(
            staff_member=staff_member,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__in=[Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT]
        ).exists():
            raise serializers.ValidationError(
                "The selected time slot is no longer available.")

        # Rule: Check user's active appointment limit based on role [RFD-APP-03]
        active_appointments = Appointment.objects.filter(
            user=user,
            status__in=[Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT]
        ).count()

        if user.role == CustomUser.Role.CLIENT and active_appointments >= 1:
            raise serializers.ValidationError(
                "As a CLIENT, you can only have 1 active appointment. Please complete or cancel your existing appointment."
            )
        if user.role == CustomUser.Role.VIP and active_appointments >= 4:
            raise serializers.ValidationError(
                "As a VIP, you can have up to 4 active appointments."
            )

        return data

    def create(self, validated_data):
        service = validated_data['service']
        user = validated_data['user']

        # Set price based on user role [RFD-PAY-02]
        price = service.vip_price if user.role == CustomUser.Role.VIP and service.vip_price is not None else service.price
        validated_data['price_at_purchase'] = price

        # Calculate end_time
        validated_data['end_time'] = validated_data['start_time'] + \
            timedelta(minutes=service.duration)

        return super().create(validated_data)


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
            raise serializers.ValidationError(
                {"service_id": "El servicio no existe o no está activo."})

        # CORRECCIÓN CRÍTICA: Convertir duración a timedelta
        service_duration = timedelta(minutes=service.duration)
        day_of_week = selected_date.weekday()

        all_availabilities = StaffAvailability.objects.filter(
            day_of_week=day_of_week).select_related('staff_member')
        booked_appointments = Appointment.objects.filter(
            start_time__date=selected_date,
            status__in=[Appointment.AppointmentStatus.PENDING,
                        Appointment.AppointmentStatus.CONFIRMED]
        )

        slots = {}
        for availability in all_availabilities:
            staff = availability.staff_member

            slot_time = datetime.combine(
                selected_date, availability.start_time)
            schedule_end_time = datetime.combine(
                selected_date, availability.end_time)

            while slot_time + service_duration <= schedule_end_time:
                slot_end = slot_time + service_duration

                is_booked = booked_appointments.filter(
                    staff_member=staff,
                    start_time__lt=slot_end,
                    end_time__gt=slot_time
                ).exists()

                if not is_booked:
                    time_str = slot_time.strftime('%H:%M')
                    if time_str not in slots:
                        slots[time_str] = []

                    slots[time_str].append({
                        "staff_id": staff.phone_number,
                        "staff_name": f"{staff.first_name} {staff.last_name}"
                    })

                slot_time += timedelta(minutes=30)

        sorted_slots = dict(sorted(slots.items()))
        return sorted_slots


class AppointmentRescheduleSerializer(serializers.Serializer):
    """
    Serializer for handling the logic of rescheduling an appointment.
    It's not a ModelSerializer because it validates an action, not a resource representation.
    """
    new_start_time = serializers.DateTimeField()

    def validate_new_start_time(self, value):
        """
        Check that the new appointment time is in the future.
        """
        if value < timezone.now():
            raise serializers.ValidationError(
                "Cannot reschedule to a time in the past.")
        return value

    def validate(self, data):
        appointment = self.context['appointment']
        new_start_time = data['new_start_time']
        user = self.context['request'].user

        # Rule [RFD-APP-06]: Must be a confirmed appointment
        if appointment.status != Appointment.AppointmentStatus.CONFIRMED:
            raise serializers.ValidationError(
                "Only confirmed appointments can be rescheduled.")

        # Rule [RFD-APP-06]: Max 2 reschedules allowed
        if appointment.reschedule_count >= 2:
            raise serializers.ValidationError(
                "This appointment has already been rescheduled the maximum number of times (2)."
            )

        # Rule [RFD-APP-06]: Must be rescheduled at least 24 hours in advance
        if appointment.start_time - timezone.now() < timedelta(hours=24):
            raise serializers.ValidationError(
                "Appointments can only be rescheduled up to 24 hours in advance."
            )

        # Re-use availability logic: check staff availability and conflicts
        service = appointment.service
        staff_member = appointment.staff_member
        new_end_time = new_start_time + timedelta(minutes=service.duration)
        day_of_week = new_start_time.isoweekday()

        if not StaffAvailability.objects.filter(
            staff_member=staff_member,
            day_of_week=day_of_week,
            start_time__lte=new_start_time.time(),
            end_time__gte=new_end_time.time()
        ).exists():
            raise serializers.ValidationError(
                "The staff member is not available at the newly selected time.")

        if Appointment.objects.filter(
            staff_member=staff_member,
            start_time__lt=new_end_time,
            end_time__gt=new_start_time,
            status__in=[Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT]
        ).exclude(pk=appointment.pk).exists():
            raise serializers.ValidationError(
                "The new time slot is conflicting with another appointment.")

        return data

    def save(self, **kwargs):
        """
        Performs the update on the appointment instance.
        """
        appointment = self.context['appointment']
        new_start_time = self.validated_data['new_start_time']

        appointment.start_time = new_start_time
        appointment.end_time = new_start_time + \
            timedelta(minutes=appointment.service.duration)
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
