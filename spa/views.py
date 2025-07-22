# spa/views.py

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
from users.models import CustomUser
from users.permissions import IsVerified, IsAdminUser, IsStaff
from profiles.permissions import IsStaffOrAdmin
from .services import calculate_available_slots, PackagePurchaseService, VipSubscriptionService 
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
    # El queryset base se define en get_queryset para mayor claridad.
    queryset = Appointment.objects.all() 
    permission_classes = [IsAuthenticated, IsVerified]

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        # Para 'list', 'retrieve' y otras acciones.
        return AppointmentListSerializer

    # --- INICIO DE LA MODIFICACIÓN ---
    def get_queryset(self):
        """
        Centraliza la lógica de obtención de citas, optimizando la consulta
        y aplicando el filtrado según el rol del usuario.
        """
        # 1. Iniciar con la consulta optimizada
        queryset = Appointment.objects.select_related(
            'user', 'service', 'staff_member'
        )

        # 2. Aplicar filtro basado en el rol del usuario
        user = self.request.user
        if user.is_staff or user.is_superuser:
            # El personal y los administradores pueden ver todas las citas
            return queryset.all()
        
        # Los usuarios regulares solo pueden ver sus propias citas
        return queryset.filter(user=user)
    # --- FIN DE LA MODIFICACIÓN ---

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        # Se devuelve la instancia usando el serializador de lista para consistencia.
        list_serializer = AppointmentListSerializer(serializer.instance, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsVerified])
    @transaction.atomic
    def reschedule(self, request, pk=None):
        appointment = self.get_object()
        # Simplificación del chequeo de permisos, DRF lo maneja.
        # El get_object() ya debería fallar si no tiene permiso, pero una doble verificación es segura.
        if appointment.user != request.user and not request.user.is_staff:
            return Response(
                {'detail': 'You do not have permission to perform this action.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(
            instance=appointment, # Es importante pasar la instancia para una actualización
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

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # ... (lógica inicial del webhook sin cambios) ...
        transaction_data = request.data.get("data", {}).get("transaction", {})
        reference = transaction_data.get("reference")
        transaction_id_wompi = transaction_data.get("id")
        transaction_status = transaction_data.get("status")

        if not all([reference, transaction_id_wompi, transaction_status]):
            return Response({"error": "Datos del webhook incompletos"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.select_for_update().get(transaction_id=reference)
            
            payment.status = transaction_status
            payment.raw_response = transaction_data
            if transaction_status == 'APPROVED':
                 # Es importante actualizar el transaction_id con el definitivo de Wompi
                payment.transaction_id = transaction_id_wompi
            payment.save()

            if transaction_status == 'APPROVED':
                if payment.payment_type == Payment.PaymentType.PACKAGE:
                    PackagePurchaseService.fulfill_purchase(payment)
                
                elif payment.payment_type == Payment.PaymentType.ADVANCE:
                    if payment.appointment:
                        payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                        payment.appointment.save()

                elif payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION:
                    # ¡Aquí conectamos nuestro nuevo servicio!
                    VipSubscriptionService.fulfill_subscription(payment)
            
            return Response(status=status.HTTP_200_OK)
        
        except Payment.DoesNotExist:
            return Response({"error": f"Pago con referencia '{reference}' no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # En producción, es vital loggear el error 'e'
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