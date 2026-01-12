"""
Acciones de usuario para crear y gestionar citas.
"""
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils.decorators import idempotent_view
from core.utils.exceptions import BusinessLogicError
from users.models import CustomUser
from users.permissions import IsVerified

from ...serializers import (
    AppointmentListSerializer,
    AvailabilityCheckSerializer,
    TipCreateSerializer,
)
from ...services import AppointmentService
from finances.payments import PaymentService
from .utils import append_cancellation_strike


class AppointmentUserActionsMixin:
    @idempotent_view(timeout=60)
    def create(self, request, *args, **kwargs):
        """Crea una nueva cita."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        try:
            service = AppointmentService(
                user=request.user,
                services=validated_data['services'],
                staff_member=validated_data.get('staff_member'),
                start_time=validated_data['start_time']
            )
            appointment = service.create_appointment_with_lock()
        except BusinessLogicError as exc:
            raise exc
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsVerified], url_path='suggestions')
    def suggestions(self, request):
        """Obtiene sugerencias de horarios disponibles."""
        params = request.query_params.copy()
        if 'service_ids' in params:
            params.setlist('service_ids', request.query_params.getlist('service_ids'))
        serializer = AvailabilityCheckSerializer(data=params)
        serializer.is_valid(raise_exception=True)
        slots = serializer.get_available_slots()
        body = {"slots": slots}
        if not slots:
            body["message"] = "No hay terapeutas disponibles para la duración solicitada en este horario."
        return Response(body, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsVerified])
    @transaction.atomic
    def reschedule(self, request, pk=None):
        """Reagenda una cita existente."""
        appointment = self.get_object()
        if appointment.user != request.user and request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
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
        new_start_time = serializer.validated_data['new_start_time']
        skip_counter = serializer.validated_data.get('skip_counter', False)

        # Solo Admin/Staff pueden usar skip_counter
        is_privileged = request.user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        if skip_counter and not is_privileged:
            skip_counter = False  # Ignorar si no es privilegiado

        try:
            updated_appointment = AppointmentService.reschedule_appointment(
                appointment=appointment,
                new_start_time=new_start_time,
                acting_user=request.user,
                skip_counter=skip_counter,
            )
        except ValidationError as exc:
            message = exc.message or (exc.messages[0] if getattr(exc, 'messages', None) else str(exc))
            return Response({'error': message}, status=422)

        list_serializer = AppointmentListSerializer(updated_appointment, context={'request': request})
        response = Response(list_serializer.data, status=status.HTTP_200_OK)

        # Solo aplicar penalidades si el cliente reagendó su propia cita Y se incrementó el contador
        if appointment.user == request.user and not skip_counter:
            history = append_cancellation_strike(
                user=appointment.user,
                appointment=updated_appointment,
                strike_type="RESCHEDULE",
                amount=Decimal('0'),
            )
            from finances.services import CreditManagementService
            CreditManagementService.apply_cancellation_penalty(appointment.user, updated_appointment, history)
        return response

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsVerified], url_path='tip')
    @transaction.atomic
    def add_tip(self, request, pk=None):
        """Agrega una propina a una cita."""
        appointment = self.get_object()
        if appointment.user != request.user and request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return Response(
                {'detail': 'You do not have permission to perform this action.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        try:
            payment = PaymentService.create_tip_payment(
                appointment=appointment,
                user=request.user,
                amount=amount,
            )
        except ValidationError as exc:
            message = exc.message or (exc.messages[0] if getattr(exc, 'messages', None) else str(exc))
            return Response({'error': message}, status=422)

        return Response(
            {
                'tip_payment_id': str(payment.id),
                'amount': str(payment.amount),
                'status': payment.status,
            },
            status=status.HTTP_201_CREATED,
        )
