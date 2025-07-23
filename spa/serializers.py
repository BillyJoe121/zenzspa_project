from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from .models import (
    ServiceCategory, Service, Package, StaffAvailability, Appointment, Payment,
    UserPackage, Voucher, PackageService # <-- 'PackageService' AHORA ESTÁ INCLUIDO AQUÍ
)
from users.serializers import SimpleUserSerializer # Se mantiene tu import original
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from core.models import GlobalSettings
from decimal import Decimal
from .services import calculate_available_slots

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


class AppointmentListSerializer(serializers.ModelSerializer):
    """
    Serializador CONSOLIDADO para leer (listar y detallar) citas.
    Utiliza serializadores de resumen para optimizar la respuesta y mejorar la seguridad.
    Este serializador reemplaza a los antiguos AppointmentReadSerializer y AppointmentListSerializer.
    """
    user = UserSummarySerializer(read_only=True)
    service = ServiceSummarySerializer(read_only=True)
    staff_member = UserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id',
            'user',
            'service',
            'staff_member',
            'start_time',
            'end_time',
            'status',
            'status_display', # Campo útil para el frontend
            'price_at_purchase',
            'reschedule_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

AppointmentReadSerializer = AppointmentListSerializer

class AppointmentCreateSerializer(serializers.ModelSerializer):
    """
    Serializador para validar los datos de entrada al crear una cita.
    La lógica de negocio compleja (validación de reglas, creación) ha sido
    movida a la capa de servicios (AppointmentService).
    """
    class Meta:
        model = Appointment
        # Solo incluimos los campos que el usuario debe enviar.
        fields = ['service', 'staff_member', 'start_time']

    def validate(self, data):
        """
        Validación básica de los datos de entrada.
        """
        service = data.get('service')
        staff_member = data.get('staff_member')

        # Regla simple: si el servicio no es de baja supervisión, el staff es obligatorio.
        if not service.category.is_low_supervision and not staff_member:
            raise serializers.ValidationError({"staff_member": "Este servicio requiere seleccionar un miembro del personal."})
        
        # Si es de baja supervisión, nos aseguramos que staff_member sea nulo.
        if service.category.is_low_supervision:
            data['staff_member'] = None
            
        return data
    
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
    service_id = serializers.UUIDField()
    date = serializers.DateField()

    # Se mueve la lógica a un método de servicio para mantener el serializador limpio
    def get_available_slots(self):
        service_id = self.validated_data['service_id']
        selected_date = self.validated_data['date']
        # La lógica pesada ahora vive en un servicio, el serializador solo lo llama
        return calculate_available_slots(service_id, selected_date)


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

        available_slots = calculate_available_slots(appointment.service.id, new_start_time.date())
        requested_time_str = new_start_time.strftime('%H:%M')

        if requested_time_str not in available_slots:
            raise serializers.ValidationError("El nuevo horario seleccionado ya no está disponible.")

        if appointment.staff_member:
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
    

class VoucherSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los Vouchers de un usuario."""
    service_name = serializers.CharField(source='service.name', read_only=True)
    # Usamos la fecha de expiración del paquete comprado
    expires_at = serializers.DateField(source='user_package.expires_at', read_only=True)
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
        write_only=True
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        # La lógica de creación del pago y el UserPackage se manejará en la vista
        # Este serializador solo valida la entrada.
        return validated_data