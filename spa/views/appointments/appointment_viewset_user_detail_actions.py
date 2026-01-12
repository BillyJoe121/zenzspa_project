"""
Acciones de usuario sobre citas existentes.
"""
import logging
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditLog
from users.models import CustomUser
from users.permissions import IsVerified

from ...models import Appointment
from ...serializers import (
    AppointmentCancelSerializer,
    AppointmentListSerializer,
)
from ...services import AppointmentService, WaitlistService
from finances.payments import PaymentService
from .utils import append_cancellation_strike

logger = logging.getLogger(__name__)


class AppointmentUserDetailActionsMixin:
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
                Appointment.AppointmentStatus.FULLY_PAID,
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

        # Cancelar pagos pendientes para evitar bloqueo por deuda
        PaymentService.cancel_pending_payments_for_appointment(appointment)

        # Revertir cashback si hubo
        try:
            from finances.services.cashback import CashbackService
            CashbackService.revert_cashback(appointment)
        except Exception as e:
            logger.error("Error reverting cashback for appointment %s: %s", appointment.id, e)

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
            and previous_status in [Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.FULLY_PAID]
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

                    # Notificar al usuario sobre el crédito generado
                    try:
                        from notifications.services import NotificationService
                        NotificationService.send_notification(
                            user=user,
                            event_code="ORDER_CREDIT_ISSUED",
                            context={
                                "user_name": user.first_name,
                                "credit_amount": f"${credit_amount:,.0f}",
                                "reason": f"Reembolso por cancelación de cita {appointment.id}",
                                "order_id": str(appointment.id) # Reutilizamos el campo order_id para el ID de la cita
                            }
                        )
                    except Exception:
                        logger.exception("Error enviando notificación de crédito por cancelación de cita %s", appointment.id)
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
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            return Response(
                {'error': 'Solo se pueden exportar citas confirmadas, reagendadas o totalmente pagadas.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ics_payload = AppointmentService.build_ical_event(appointment)
        response = HttpResponse(ics_payload, content_type='text/calendar')
        response['Content-Disposition'] = f'attachment; filename=appointment-{appointment.id}.ics'
        return response

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsVerified], url_path='available-actions')
    def available_actions(self, request, pk=None):
        """
        Returns which actions are available for this appointment.

        This endpoint centralizes business logic for showing/hiding action buttons
        in the frontend. Instead of hardcoding state checks in the UI, the frontend
        can call this endpoint to know exactly which actions are permitted.

        GET /api/appointments/{id}/available-actions/

        Response:
        {
            "can_reschedule": true,
            "can_reschedule_reason": "",
            "can_cancel": true,
            "can_cancel_reason": "",
            "can_mark_completed": false,
            "can_mark_completed_reason": "Solo el personal puede marcar citas como completadas",
            "can_mark_no_show": false,
            "can_mark_no_show_reason": "Solo el personal puede marcar no-show",
            "can_complete_final_payment": false,
            "can_complete_final_payment_reason": "Solo el personal puede procesar pagos",
            "can_add_tip": true,
            "can_add_tip_reason": "",
            "can_download_ical": true,
            "can_download_ical_reason": "",
            "can_cancel_by_admin": false,
            "can_cancel_by_admin_reason": "Solo administradores pueden usar esta acción",
            "status": "CONFIRMED",
            "is_active": true,
            "is_past": false,
            "hours_until": 48.5
        }
        """
        appointment = self.get_object()
        user = request.user

        # Check all available actions
        can_reschedule, reschedule_reason = appointment.can_reschedule(user)
        can_cancel, cancel_reason = appointment.can_cancel(user)
        can_mark_completed, mark_completed_reason = appointment.can_mark_completed(user)
        can_mark_no_show, mark_no_show_reason = appointment.can_mark_no_show(user)
        can_complete_final_payment, complete_final_payment_reason = appointment.can_complete_final_payment(user)
        can_add_tip, add_tip_reason = appointment.can_add_tip(user)
        can_download_ical, download_ical_reason = appointment.can_download_ical(user)
        can_cancel_by_admin, cancel_by_admin_reason = appointment.can_cancel_by_admin(user)

        return Response({
            # Reschedule action
            'can_reschedule': can_reschedule,
            'can_reschedule_reason': reschedule_reason,

            # Cancel action (client)
            'can_cancel': can_cancel,
            'can_cancel_reason': cancel_reason,

            # Mark completed (staff)
            'can_mark_completed': can_mark_completed,
            'can_mark_completed_reason': mark_completed_reason,

            # Mark no-show (staff)
            'can_mark_no_show': can_mark_no_show,
            'can_mark_no_show_reason': mark_no_show_reason,

            # Complete final payment (staff)
            'can_complete_final_payment': can_complete_final_payment,
            'can_complete_final_payment_reason': complete_final_payment_reason,

            # Add tip
            'can_add_tip': can_add_tip,
            'can_add_tip_reason': add_tip_reason,

            # Download iCal
            'can_download_ical': can_download_ical,
            'can_download_ical_reason': download_ical_reason,

            # Cancel by admin (admin only)
            'can_cancel_by_admin': can_cancel_by_admin,
            'can_cancel_by_admin_reason': cancel_by_admin_reason,

            # Additional helpful info
            'status': appointment.status,
            'status_display': appointment.get_status_display(),
            'is_active': appointment.is_active,
            'is_past': appointment.is_past,
            'is_upcoming': appointment.is_upcoming,
            'hours_until': round(appointment.hours_until_appointment, 1),
            'reschedule_count': appointment.reschedule_count,
        }, status=status.HTTP_200_OK)
