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
from users.permissions import IsVerified, IsAdminUser
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
            self.permission_classes = [IsAdminOrOwnerOfAvailability]
        else:
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.role == CustomUser.Role.ADMIN:
            return StaffAvailability.objects.all().select_related('staff_member')
        if user.role == CustomUser.Role.STAFF:
            return StaffAvailability.objects.filter(staff_member=user).select_related('staff_member')
        return StaffAvailability.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == CustomUser.Role.STAFF:
            serializer.save(staff_member=user)
        elif user.role == CustomUser.Role.ADMIN:
            serializer.save()


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing appointments.
    """
    queryset = Appointment.objects.select_related(
        'user', 'service', 'staff_member').all()
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se añade el permiso IsVerified. Ahora se requiere estar autenticado Y verificado.
    permission_classes = [IsAuthenticated, IsVerified]
    # --- FIN DE LA MODIFICACIÓN ---

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

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser]) # Solo el Admin puede cancelar así
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
    # Se añade el permiso IsVerified para asegurar que solo usuarios verificados inicien pagos.
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
    # Se añade el permiso IsVerified para que solo usuarios verificados puedan consultar disponibilidad.
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = AvailabilityCheckSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        available_slots = serializer.get_available_slots()
        return Response(available_slots, status=status.HTTP_200_OK)