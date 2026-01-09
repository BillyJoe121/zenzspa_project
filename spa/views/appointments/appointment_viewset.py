"""
ViewSet principal para gestión de citas (appointments).
"""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from legal.models import LegalDocument, UserConsent
from legal.permissions import consent_required_permission
from users.models import CustomUser
from users.permissions import IsVerified

from ...models import Appointment
from ...serializers import (
    AppointmentCreateSerializer,
    AppointmentListSerializer,
    AppointmentRescheduleSerializer,
)
from .appointment_viewset_admin_actions import AppointmentAdminActionsMixin
from .appointment_viewset_admin_create import AppointmentAdminCreateMixin
from .appointment_viewset_user_actions import AppointmentUserActionsMixin
from .appointment_viewset_user_detail_actions import AppointmentUserDetailActionsMixin
from .appointment_viewset_waitlist_actions import AppointmentWaitlistActionsMixin


class AppointmentViewSet(
    AppointmentUserActionsMixin,
    AppointmentUserDetailActionsMixin,
    AppointmentWaitlistActionsMixin,
    AppointmentAdminActionsMixin,
    AppointmentAdminCreateMixin,
    viewsets.ModelViewSet,
):
    """ViewSet para gestión completa de citas."""
    queryset = Appointment.objects.all()
    permission_classes = [IsAuthenticated, IsVerified]

    def get_permissions(self):
        base = super().get_permissions()
        if self.action in ['create', 'reschedule', 'suggestions']:
            base.append(
                consent_required_permission(
                    LegalDocument.DocumentType.PROFILE,
                    context_type=UserConsent.ContextType.APPOINTMENT,
                )()
            )
        return base

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def get_queryset(self):
        """
        Retorna las citas según el rol del usuario.

        Para Staff/Admin: Todas las citas, con filtros opcionales:
        - user_id: UUID del usuario para ver sus citas
        - status: filtrar por estado (CONFIRMED, CANCELLED, etc.)
        - date: filtrar por fecha específica (YYYY-MM-DD)
        - date_from: filtrar desde esta fecha
        - date_to: filtrar hasta esta fecha

        Para clientes: Solo sus propias citas.
        """
        queryset = Appointment.objects.select_related(
            'user', 'staff_member'
        ).prefetch_related('items__service')
        user = self.request.user

        if user.is_staff or user.is_superuser or user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            # Admin/Staff puede ver todas las citas
            queryset = queryset.all()

            # Filtro por usuario específico
            user_id = self.request.query_params.get('user_id')
            if user_id:
                queryset = queryset.filter(user_id=user_id)

            # Filtro por estado
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)

            # Filtro por fecha exacta
            date_filter = self.request.query_params.get('date')
            if date_filter:
                queryset = queryset.filter(start_time__date=date_filter)

            # Filtro por rango de fechas
            date_from = self.request.query_params.get('date_from')
            if date_from:
                queryset = queryset.filter(start_time__date__gte=date_from)

            date_to = self.request.query_params.get('date_to')
            if date_to:
                queryset = queryset.filter(start_time__date__lte=date_to)

            return queryset.order_by('-start_time')

        # Clientes solo ven sus propias citas
        return queryset.filter(user=user).order_by('-start_time')
