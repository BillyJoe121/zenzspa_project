import hashlib
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.conf import settings
from django.db.models import ProtectedError # <--- IMPORTAR ProtectedError
from core.models import AuditLog
from django.db import transaction
from django.shortcuts import get_object_or_404
from users.models import CustomUser
from users.permissions import IsVerified, IsAdminUser, IsStaff
from profiles.permissions import IsStaffOrAdmin
from .services import calculate_available_slots
from .permissions import IsAdminOrOwnerOfAvailability, IsAdminOrReadOnly
from .models import (
    ServiceCategory, Service, Package, Appointment, StaffAvailability, Payment
)
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, PackageSerializer,
    AppointmentReadSerializer, AppointmentCreateSerializer,
    AppointmentStatusUpdateSerializer, StaffAvailabilitySerializer,
    AvailabilityCheckSerializer, AppointmentListSerializer,
    AppointmentRescheduleSerializer
)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    # --- INICIO DE LA MODIFICACIÓN ---
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
    # --- FIN DE LA MODIFICACIÓN ---


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]


class PackageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Package.objects.filter(is_active=True)
    serializer_class = PackageSerializer
    permission_classes = [AllowAny]

class StaffAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = StaffAvailabilitySerializer
    permission_classes = [IsAuthenticated, (IsAdminUser | IsStaff)]

    def get_queryset(self):
        user = self.request.user
        if user.role == CustomUser.Role.ADMIN:
            return StaffAvailability.objects.all().select_related('staff_member')
        return StaffAvailability.objects.filter(staff_member=user).select_related('staff_member')

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == CustomUser.Role.STAFF:
            serializer.save(staff_member=user)
        elif user.role == CustomUser.Role.ADMIN:
            serializer.save()

class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related(
        'user', 'service', 'staff_member').all()
    permission_classes = [IsAuthenticated, IsVerified]

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return super().get_queryset()
        return super().get_queryset().filter(user=user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        list_serializer = AppointmentListSerializer(serializer.instance)
        return Response(list_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
            data=request.data,
            context={'request': request, 'appointment': appointment}
        )
        serializer.is_valid(raise_exception=True)
        updated_appointment = serializer.save()
        list_serializer = AppointmentListSerializer(updated_appointment)
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
        list_serializer = AppointmentListSerializer(appointment)
        return Response(list_serializer.data, status=status.HTTP_200_OK)


class InitiatePaymentView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment, pk=pk, user=request.user)
        amount_in_cents = int(appointment.price_at_booking * 100)
        reference = f"APPOINTMENT-{appointment.pk}"
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
        event_data = request.data
        transaction_data = event_data.get("data", {}).get("transaction", {})
        reference = transaction_data.get("reference")
        transaction_id = transaction_data.get("id")
        transaction_status = transaction_data.get("status")
        if not all([reference, transaction_id, transaction_status]):
            return Response({"error": "Datos del webhook incompletos"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                appointment = None
                if reference.startswith("APPOINTMENT-"):
                    appointment_id = reference.split('-')[1]
                    appointment = Appointment.objects.select_for_update().get(id=appointment_id)
                else:
                    raise ValueError("Referencia de pago no válida")
                Payment.objects.update_or_create(
                    gateway_transaction_id=transaction_id,
                    defaults={'appointment': appointment, 'amount': transaction_data.get(
                        "amount_in_cents", 0) / 100, 'status': transaction_status}
                )
                if transaction_status == 'APPROVED' and appointment:
                    appointment.status = Appointment.AppointmentStatus.CONFIRMED
                    appointment.save()
            return Response(status=status.HTTP_200_OK)
        except (Appointment.DoesNotExist, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AvailabilityCheckView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = AvailabilityCheckSerializer

    def get(self, request, *args, **kwargs):
        """
        Maneja peticiones GET para consultar la disponibilidad.
        Los parámetros se pasan como query params: ?service_id=<uuid>&date=YYYY-MM-DD
        """
        # Usamos el serializador para validar los query params
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        
        service_id = serializer.validated_data['service_id']
        selected_date = serializer.validated_data['date']

        # Llama a la lógica de negocio centralizada en el servicio
        available_slots = calculate_available_slots(service_id, selected_date)
        
        return Response(available_slots, status=status.HTTP_200_OK)