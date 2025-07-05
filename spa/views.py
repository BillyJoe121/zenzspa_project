import hashlib
from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.conf import settings
from core.models import AuditLog
from django.db import transaction
from django.shortcuts import get_object_or_404
from users.models import CustomUser
from profiles.permissions import IsStaffOrAdmin
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

    def get_permissions(self):
        """Asigna permisos basados en la acción."""
        if self.action in ['update', 'partial_update', 'destroy']:
            # Para modificar o borrar un objeto, se necesita ser admin o el dueño.
            self.permission_classes = [IsAdminOrOwnerOfAvailability]
        else:
            # Para listar o crear, solo se necesita estar autenticado.
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        # Los administradores pueden ver todos los horarios de disponibilidad.
        if user.role == CustomUser.Role.ADMIN:
            return StaffAvailability.objects.all().select_related('staff_member')
        # El personal solo puede ver su propia disponibilidad.
        if user.role == CustomUser.Role.STAFF:
            return StaffAvailability.objects.filter(staff_member=user).select_related('staff_member')
        # Otros roles (como clientes) no ven ningún horario.
        return StaffAvailability.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        # Si el usuario es STAFF, el horario se le asigna a él mismo automáticamente.
        if user.role == CustomUser.Role.STAFF:
            serializer.save(staff_member=user)
        # Si es ADMIN, el 'staff_member_id' debe venir en el request body.
        elif user.role == CustomUser.Role.ADMIN:
            serializer.save()


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing appointments.
    """
    queryset = Appointment.objects.select_related(
        'user', 'service', 'staff_member').all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        # Add other actions that need a different serializer here
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def get_queryset(self):
        """
        Users can only see their own appointments.
        Staff/Admins can see all appointments.
        """
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
        # We return the ListSerializer representation for consistency
        list_serializer = AppointmentListSerializer(serializer.instance)
        return Response(list_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def reschedule(self, request, pk=None):
        """
        Custom action to reschedule a confirmed appointment.
        """
        appointment = self.get_object()

        # Security check: Ensure the user owns the appointment
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

        # Return the updated appointment using the list serializer
        list_serializer = AppointmentListSerializer(updated_appointment)
        return Response(list_serializer.data, status=status.HTTP_200_OK)

        # Dentro de la clase AppointmentViewSet en spa/views.py

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrOwnerOfAvailability])
    @transaction.atomic
    def cancel_by_admin(self, request, pk=None):
        """
        Custom action for an Admin to cancel a confirmed appointment.
        This action creates an audit log entry.
        """
        appointment = self.get_object()

        if appointment.status != Appointment.AppointmentStatus.CONFIRMED:
            return Response(
                {'error': 'Only confirmed appointments can be cancelled by an admin.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Change status
        appointment.status = Appointment.AppointmentStatus.CANCELLED_BY_ADMIN
        appointment.save()

        # Create the audit log entry
        AuditLog.objects.create(
            admin_user=request.user,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
            target_user=appointment.user,
            target_appointment=appointment,  # Link to the specific appointment
            details=f"Admin '{request.user.get_full_name()}' cancelled appointment ID {appointment.id}."
        )

        list_serializer = self.get_serializer(appointment)
        return Response(list_serializer.data, status=status.HTTP_200_OK)


class InitiatePaymentView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment, pk=pk, user=request.user)

        # Lógica de pago... (sin cambios)
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
        # Lógica del webhook... (sin cambios)
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
    """
    Endpoint para consultar la disponibilidad. Usa POST para la consulta.
    La lógica de negocio está encapsulada en el serializador.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AvailabilityCheckSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        available_slots = serializer.get_available_slots()
        return Response(available_slots, status=status.HTTP_200_OK)
