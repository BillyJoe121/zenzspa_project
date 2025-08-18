import hashlib
import uuid
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.conf import settings
from django.db.models import ProtectedError
from core.models import AuditLog
from core.models import AuditLog, GlobalSettings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from users.models import CustomUser
from users.permissions import IsVerified, IsAdminUser, IsStaff
from profiles.permissions import IsStaffOrAdmin
from .services import calculate_available_slots, PackagePurchaseService, VipSubscriptionService, AppointmentService, WompiWebhookService
from .permissions import IsAdminOrOwnerOfAvailability, IsAdminOrReadOnly
from .models import (
    ServiceCategory, Service, Package, Appointment, StaffAvailability, Payment,
    UserPackage, Voucher # Nuevos modelos
)
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, PackageSerializer,
    AppointmentReadSerializer, AppointmentCreateSerializer,
    AppointmentStatusUpdateSerializer, StaffAvailabilitySerializer,
    AvailabilityCheckSerializer, AppointmentListSerializer,
    AppointmentRescheduleSerializer,
    # Nuevos serializadores
    UserPackageDetailSerializer,
    VoucherSerializer,
    PackagePurchaseCreateSerializer
)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        """
        Sobrescribe el método de eliminación para manejar la protección
        de integridad referencial de forma elegante.
        """
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProtectedError:
            return Response(
                {"error": "Esta categoría no puede ser eliminada porque todavía tiene servicios asociados. Por favor, reasigne o elimine los servicios primero."},
                status=status.HTTP_400_BAD_REQUEST
            )


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]


class PackageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Package.objects.filter(is_active=True)
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

class StaffAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = StaffAvailabilitySerializer
    permission_classes = [IsAuthenticated, (IsAdminUser | IsStaff)]

    def get_queryset(self):
        user = self.request.user
        base_queryset = StaffAvailability.objects.select_related('staff_member')
        if user.role == CustomUser.Role.ADMIN:
            return base_queryset.all()
        # Asumiendo que el perfil de staff está en el usuario
        return base_queryset.filter(staff_member=user)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == CustomUser.Role.STAFF:
            serializer.save(staff_member=user)
        elif user.role == CustomUser.Role.ADMIN:
            # En creación por admin, el 'staff_member' debe venir en el payload
            serializer.save()

class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all() 
    permission_classes = [IsAuthenticated, IsVerified]

    def get_serializer_class(self):
        # ... (Sin cambios)
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def get_queryset(self):
        # ... (Sin cambios)
        queryset = Appointment.objects.select_related(
            'user', 'service', 'staff_member'
        )
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset.all()
        return queryset.filter(user=user)

    # Se sobrescribe el método 'create' para usar el servicio.
    def create(self, request, *args, **kwargs):
        # 1. Usar el serializador para validar el formato de los datos de entrada
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # 2. Instanciar y llamar al servicio con los datos validados
        try:
            service = AppointmentService(
                user=request.user,
                service=validated_data['service'],
                staff_member=validated_data.get('staff_member'),
                start_time=validated_data['start_time']
            )
            appointment = service.create_appointment_with_lock()
        except ValueError as e:
            # Capturamos los errores de validación de negocio del servicio
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        # 3. Serializar la respuesta y enviarla
        response_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    # El método perform_create ya no es necesario para la acción 'create'
    # Se mantiene por si DRF lo usa en otras acciones, pero podría eliminarse si no.
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsVerified])
    @transaction.atomic
    def reschedule(self, request, pk=None):
        appointment = self.get_object()
        if appointment.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to perform this action.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = self.get_serializer(
            instance=appointment,
            data=request.data,
            context={'request': request, 'appointment': appointment}
        )
        serializer.is_valid(raise_exception=True)
        updated_appointment = serializer.save()
        list_serializer = AppointmentListSerializer(updated_appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    @transaction.atomic
    def cancel_by_admin(self, request, pk=None):
        appointment = self.get_object()
        mark_as_refunded = request.data.get('mark_as_refunded', False)

        if appointment.status != Appointment.AppointmentStatus.CONFIRMED:
            return Response(
                {'error': 'Only confirmed appointments can be cancelled by an admin.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = Appointment.AppointmentStatus.CANCELLED_BY_ADMIN
        appointment.save()
        AuditLog.objects.create(
            admin_user=request.user,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
            target_user=appointment.user,
            target_appointment=appointment,
            details=f"Admin '{request.user.first_name}' cancelled appointment ID {appointment.id}."
        )
        if mark_as_refunded:
            appointment.status = Appointment.AppointmentStatus.REFUNDED
            appointment.save(update_fields=['status'])
            
            # (Opcional pero recomendado) Crear un nuevo tipo de acción en AuditLog para reembolsos.
            # Por ahora, usamos la misma acción con detalles adicionales.
            AuditLog.objects.create(
                admin_user=request.user,
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN, # Considerar crear 'APPOINTMENT_REFUNDED'
                target_user=appointment.user,
                target_appointment=appointment,
                details=f"Admin '{request.user.first_name}' marked appointment ID {appointment.id} as REFUNDED."
            )
        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin])
    def mark_as_no_show(self, request, pk=None):
        """
        Permite al personal marcar una cita confirmada como 'No Asistió'.
        """
        appointment = self.get_object()

        # Validación 1: Solo se puede marcar si la cita estaba confirmada.
        if appointment.status != Appointment.AppointmentStatus.CONFIRMED:
            return Response(
                {'error': 'Solo las citas confirmadas pueden ser marcadas como "No Asistió".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validación 2: Solo se puede marcar si la hora de la cita ya pasó.
        if appointment.start_time > timezone.now():
            return Response(
                {'error': 'No se puede marcar como "No Asistió" una cita que aún no ha ocurrido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment.status = Appointment.AppointmentStatus.NO_SHOW
        appointment.save(update_fields=['status'])

        # (Opcional pero recomendado) Crear un log de auditoría para esta acción.
        AuditLog.objects.create(
            admin_user=request.user,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN, # Considerar crear 'APPOINTMENT_NO_SHOW'
            target_user=appointment.user,
            target_appointment=appointment,
            details=f"Staff '{request.user.first_name}' marked appointment ID {appointment.id} as NO SHOW."
        )

        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

class UserPackageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint de solo lectura para que un usuario vea los paquetes que ha comprado.
    """
    serializer_class = UserPackageDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra los paquetes para que solo muestre los del usuario autenticado."""
        return UserPackage.objects.filter(user=self.request.user).select_related('package').prefetch_related('vouchers__service')

class VoucherViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint de solo lectura para que un usuario vea sus vouchers disponibles, usados y expirados.
    """
    serializer_class = VoucherSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra los vouchers para que solo muestre los del usuario autenticado."""
        return Voucher.objects.filter(user=self.request.user).select_related('service', 'user_package')

class InitiatePackagePurchaseView(generics.CreateAPIView):
    """
    Vista para iniciar la compra de un paquete. Valida el paquete
    y devuelve la información para la pasarela de pago.
    """
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = PackagePurchaseCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        package = serializer.validated_data['package']
        user = request.user

        # Referencia única para el pago del paquete
        reference = f"PACKAGE-{package.id}-{uuid.uuid4().hex[:8]}"
        amount_in_cents = int(package.price * 100)

        # Crear el registro de pago en estado PENDIENTE
        Payment.objects.create(
            user=user,
            amount=package.price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.PACKAGE,
            transaction_id=reference # Usamos la referencia como transaction_id inicial
        )

        # Generar la firma de integridad para Wompi
        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class InitiateAppointmentPaymentView(generics.GenericAPIView):
    """
    Toma una cita con pago de anticipo pendiente, encuentra su registro
    de Pago asociado y genera los datos para la pasarela.
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request, pk):
        # 1. Obtenemos la cita y validamos que le pertenezca al usuario
        appointment = get_object_or_404(Appointment, pk=pk, user=request.user)

        # 2. Validamos el estado de la cita
        if appointment.status != Appointment.AppointmentStatus.PENDING_ADVANCE:
            return Response(
                {"error": "Esta cita no tiene un pago de anticipo pendiente."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. Buscamos el pago PENDIENTE asociado a esta cita
        try:
            payment = appointment.payments.get(status=Payment.PaymentStatus.PENDING)
        except Payment.DoesNotExist:
             return Response(
                {"error": "No se encontró un registro de pago pendiente para esta cita."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. Generamos la referencia y la firma
        amount_in_cents = int(payment.amount * 100)
        # Usamos el ID del pago como referencia para garantizar unicidad
        reference = f"APPOINTMENT-{appointment.id}-PAYMENT-{payment.id}"
        
        # Actualizamos el payment con la referencia que enviaremos a Wompi
        payment.transaction_id = reference
        payment.save()
        
        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()
        
        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)
    
class WompiWebhookView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        """
        Punto de entrada para los webhooks de Wompi.
        Delega toda la lógica de validación y procesamiento al WompiWebhookService.
        """
        webhook_service = WompiWebhookService(request.data)
        event_type = webhook_service.event_type
        
        try:
            if event_type == "transaction.updated":
                result = webhook_service.process_transaction_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            else:
                # Respondemos con 200 OK incluso para eventos no manejados,
                # para que Wompi no siga reintentando.
                return Response({"status": "event_type_not_handled"}, status=status.HTTP_200_OK)

        except ValueError as e:
            # Captura errores de validación (ej. firma inválida) del servicio.
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Captura cualquier otro error inesperado. Es vital loggear 'e' en producción.
            return Response({"error": "Error interno del servidor al procesar el webhook."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AvailabilityCheckView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = AvailabilityCheckSerializer

    def get(self, request, *args, **kwargs):
        """
        Maneja peticiones GET para consultar la disponibilidad.
        Los parámetros se pasan como query params: ?service_id=<uuid>&date=YYYY-MM-DD
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        service_id = serializer.validated_data['service_id']
        selected_date = serializer.validated_data['date']

        available_slots = calculate_available_slots(service_id, selected_date)
        
        return Response(available_slots, status=status.HTTP_200_OK)
    
class InitiateVipSubscriptionView(generics.GenericAPIView):
    """
    Vista para que un usuario inicie la compra/renovación de su membresía VIP.
    """
    permission_classes = [IsAuthenticated, IsVerified]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        settings = GlobalSettings.load()
        vip_price = settings.vip_monthly_price

        if vip_price is None or vip_price <= 0:
            return Response(
                {"error": "El precio de la membresía VIP no está configurado en el sistema."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Creamos una referencia única para este intento de pago
        reference = f"VIP-{user.id}-{uuid.uuid4().hex[:8]}"
        amount_in_cents = int(vip_price * 100)

        # Creamos el registro de Pago en estado PENDIENTE
        Payment.objects.create(
            user=user,
            amount=vip_price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.VIP_SUBSCRIPTION,
            transaction_id=reference
        )

        # Generamos la firma para la pasarela de pago (Wompi)
        concatenation = f"{reference}{amount_in_cents}COP{settings.WOMPI_INTEGRITY_SECRET}"
        signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signature:integrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL
        }
        return Response(payment_data, status=status.HTTP_200_OK)    