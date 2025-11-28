"""
ViewSet principal para gestión de citas (appointments).
"""
import logging
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.decorators import idempotent_view
from core.exceptions import BusinessLogicError
from core.models import AuditLog, GlobalSettings
from profiles.permissions import IsStaffOrAdmin
from users.models import CustomUser
from users.permissions import IsVerified, IsAdminUser

from ...models import Appointment, Service, WaitlistEntry
from ...serializers import (
    AppointmentCancelSerializer,
    AppointmentCreateSerializer,
    AppointmentListSerializer,
    AppointmentRescheduleSerializer,
    AvailabilityCheckSerializer,
    TipCreateSerializer,
    WaitlistConfirmSerializer,
    WaitlistJoinSerializer,
)
from ...services import (
    AppointmentService,
    WaitlistService,
)
from finances.payments import PaymentService
from .utils import append_cancellation_strike

logger = logging.getLogger(__name__)


class AppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet para gestión completa de citas."""
    queryset = Appointment.objects.all()
    permission_classes = [IsAuthenticated, IsVerified]

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def get_queryset(self):
        queryset = Appointment.objects.select_related(
            'user', 'staff_member'
        ).prefetch_related('items__service')
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset.all()
        return queryset.filter(user=user)

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
        try:
            updated_appointment = AppointmentService.reschedule_appointment(
                appointment=appointment,
                new_start_time=new_start_time,
                acting_user=request.user,
            )
        except ValidationError as exc:
            message = exc.message or (exc.messages[0] if getattr(exc, 'messages', None) else str(exc))
            return Response({'error': message}, status=422)

        list_serializer = AppointmentListSerializer(updated_appointment, context={'request': request})
        response = Response(list_serializer.data, status=status.HTTP_200_OK)
        if appointment.user == request.user:
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

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin], url_path='complete_final_payment')
    @transaction.atomic
    def complete_final_payment(self, request, pk=None):
        """Completa el pago final de una cita."""
        appointment = self.get_object()
        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]:
            return Response(
                {'error': 'Solo se pueden completar pagos finales de citas confirmadas.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment, outstanding = PaymentService.create_final_payment(appointment, request.user)
        response_data = {
            'appointment_id': str(appointment.id),
            'status': appointment.status,
            'outstanding_amount': str(outstanding),
            'final_payment_id': str(payment.id) if payment else None,
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin], url_path='mark_completed')
    @transaction.atomic
    def mark_completed(self, request, pk=None):
        """Marca una cita como completada."""
        appointment = self.get_object()
        try:
            updated = AppointmentService.complete_appointment(appointment, request.user)
        except ValidationError as exc:
            message = exc.message or (exc.messages[0] if getattr(exc, 'messages', None) else str(exc))
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AppointmentListSerializer(updated, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    @transaction.atomic
    def cancel_by_admin(self, request, pk=None):
        """Cancela una cita como administrador."""
        appointment = self.get_object()
        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('cancellation_reason', '')
        mark_as_refunded = request.data.get('mark_as_refunded', False)

        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]:
            return Response(
                {'error': 'Solo se pueden cancelar citas confirmadas o reagendadas.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.outcome = Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN
        appointment.save(update_fields=['status', 'outcome', 'updated_at'])
        AuditLog.objects.create(
            admin_user=request.user,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
            target_user=appointment.user,
            target_appointment=appointment,
            details=f"Admin '{request.user.first_name}' cancelled appointment ID {appointment.id}. Motivo: {reason or 'N/A'}.")
        if mark_as_refunded:
            appointment.outcome = Appointment.AppointmentOutcome.REFUNDED
            appointment.save(update_fields=['outcome', 'updated_at'])
            from finances.services import CreditManagementService
            CreditManagementService.issue_credit_from_appointment(
                appointment=appointment,
                percentage=Decimal('1'),
                created_by=request.user,
                reason=f"Reembolso admin cita {appointment.id}",
            )
            AuditLog.objects.create(
                admin_user=request.user,
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
                target_user=appointment.user,
                target_appointment=appointment,
                details=f"Admin '{request.user.first_name}' marked appointment ID {appointment.id} as REFUNDED."
            )
        WaitlistService.offer_slot_for_appointment(appointment)
        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsVerified], url_path='waitlist/join')
    def waitlist_join(self, request):
        """Unirse a la lista de espera."""
        WaitlistService.ensure_enabled()
        serializer = WaitlistJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service_ids = serializer.validated_data.get('service_ids') or []
        services = Service.objects.filter(id__in=service_ids, is_active=True)
        if service_ids and services.count() != len(set(service_ids)):
            return Response({'error': 'Alguno de los servicios no existe o está inactivo.'}, status=422)

        entry = WaitlistEntry.objects.create(
            user=request.user,
            desired_date=serializer.validated_data['desired_date'],
            notes=serializer.validated_data.get('notes', ''),
        )
        if services:
            entry.services.set(services)
        response = {
            'id': str(entry.id),
            'status': entry.status,
            'desired_date': entry.desired_date,
        }
        return Response(response, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAuthenticated, IsVerified],
        url_path=r'waitlist/(?P<waitlist_id>[0-9a-fA-F-]+)/confirm',
    )
    def waitlist_confirm(self, request, waitlist_id=None):
        """Confirma o rechaza una oferta de la lista de espera."""
        WaitlistService.ensure_enabled()
        with transaction.atomic():
            entry = get_object_or_404(
                WaitlistEntry.objects.select_for_update(),
                id=waitlist_id,
                user=request.user,
            )
            serializer = WaitlistConfirmSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            accept = serializer.validated_data['accept']

            if entry.status != WaitlistEntry.Status.OFFERED:
                return Response({'error': 'La lista de espera no tiene una oferta activa.'}, status=400)

            now = timezone.now()
            if entry.offer_expires_at and now > entry.offer_expires_at:
                entry.status = WaitlistEntry.Status.EXPIRED
                entry.save(update_fields=['status', 'updated_at'])
                WaitlistService.offer_slot_for_appointment(entry.offered_appointment)
                return Response({'error': 'La oferta ya no está disponible.'}, status=409)

            if not accept:
                entry.reset_offer()
                WaitlistService.offer_slot_for_appointment(entry.offered_appointment)
                return Response({'detail': 'Has rechazado el turno. Avisaremos al siguiente cliente.'}, status=status.HTTP_200_OK)

            entry.status = WaitlistEntry.Status.CONFIRMED
            entry.save(update_fields=['status', 'updated_at'])
        return Response({'detail': 'Has confirmado el turno disponible.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsVerified])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """Cancela una cita."""
        appointment = self.get_object()
        user = request.user
        if appointment.user != user and user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return Response(
                {'detail': 'You do not have permission to perform this action.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if (
            appointment.status in [
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.RESCHEDULED,
            ]
            and user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        ):
            time_until = appointment.start_time - timezone.now()
            if time_until < timedelta(hours=24):
                return Response(
                    {'error': 'Esta cita ya fue pagada. Por favor usa la opción de reagendar.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('cancellation_reason', '')
        previous_status = appointment.status
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.outcome = (
            Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN
            if user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
            else Appointment.AppointmentOutcome.CANCELLED_BY_CLIENT
        )
        appointment.save(update_fields=['status', 'outcome', 'updated_at'])
        AuditLog.objects.create(
            admin_user=user if user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF] else None,
            target_user=appointment.user,
            target_appointment=appointment,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
            details=f"Cita {appointment.id} cancelada por {'staff/admin' if user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF] else 'cliente'}. Motivo: {reason or 'N/A'}",
        )
        WaitlistService.offer_slot_for_appointment(appointment)
        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        response_payload = list_serializer.data
        strike_credit = None
        credit_amount = Decimal('0')
        if (
            appointment.outcome == Appointment.AppointmentOutcome.CANCELLED_BY_CLIENT
            and previous_status == Appointment.AppointmentStatus.CONFIRMED
        ):
            if appointment.start_time - timezone.now() >= timedelta(hours=24):
                from finances.services import CreditManagementService
                credit_amount, created_credits = CreditManagementService.issue_credit_from_appointment(
                    appointment=appointment,
                    percentage=Decimal('1'),
                    created_by=user,
                    reason=f"Cancelación con anticipación cita {appointment.id}",
                )
                if credit_amount > 0:
                    strike_credit = created_credits[0] if created_credits else None
                    response_payload['credit_generated'] = str(credit_amount)
        if appointment.user == user:
            history = append_cancellation_strike(
                user=appointment.user,
                appointment=appointment,
                strike_type="CANCEL",
                credit=strike_credit,
                amount=credit_amount,
            )
            from finances.services import CreditManagementService
            CreditManagementService.apply_cancellation_penalty(appointment.user, appointment, history)
        return Response(response_payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin])
    def mark_as_no_show(self, request, pk=None):
        """Marca una cita como 'No Asistió'."""
        appointment = self.get_object()
        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]:
            return Response(
                {'error': 'Solo las citas confirmadas pueden ser marcadas como "No Asistió".'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if appointment.start_time > timezone.now():
            return Response(
                {'error': 'No se puede marcar como "No Asistió" una cita que aún no ha ocurrido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.outcome = Appointment.AppointmentOutcome.NO_SHOW
        appointment.save(update_fields=['status', 'outcome', 'updated_at'])

        settings_obj = GlobalSettings.load()
        credit_generated = Decimal('0')
        if settings_obj.no_show_credit_policy != GlobalSettings.NoShowCreditPolicy.NONE:
            percentage = Decimal('1') if settings_obj.no_show_credit_policy == GlobalSettings.NoShowCreditPolicy.FULL else Decimal('0.5')
            from finances.services import CreditManagementService
            credit_generated, _ = CreditManagementService.issue_credit_from_appointment(
                appointment=appointment,
                percentage=percentage,
                created_by=request.user,
                reason=f"Crédito generado por No-Show cita {appointment.id}",
            )

        AuditLog.objects.create(
            admin_user=request.user,
            action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
            target_user=appointment.user,
            target_appointment=appointment,
            details=f"Staff '{request.user.first_name}' marked appointment ID {appointment.id} as NO SHOW."
        )

        notification_context = {
            "appointment_id": str(appointment.id),
            "start_time": appointment.start_time.isoformat(),
            "credit_amount": str(credit_generated),
        }
        event_code = "APPOINTMENT_NO_SHOW_PENALTY"
        if credit_generated > 0:
            event_code = "APPOINTMENT_NO_SHOW_CREDIT"
        try:
            from notifications.services import NotificationService
            NotificationService.send_notification(
                user=appointment.user,
                event_code=event_code,
                context=notification_context,
            )
        except Exception:
            logger.exception("No se pudo enviar notificación de No-Show para la cita %s", appointment.id)

        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsVerified], url_path='ical')
    def download_ical(self, request, pk=None):
        """Descarga una cita en formato iCal."""
        appointment = self.get_object()
        if appointment.user != request.user and request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return Response(
                {'detail': 'You do not have permission to perform this action.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]:
            return Response(
                {'error': 'Solo se pueden exportar citas confirmadas.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ics_payload = AppointmentService.build_ical_event(appointment)
        response = HttpResponse(ics_payload, content_type='text/calendar')
        response['Content-Disposition'] = f'attachment; filename=appointment-{appointment.id}.ics'
        return response
