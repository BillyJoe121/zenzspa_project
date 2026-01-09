"""
Acciones administrativas para citas.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import AuditLog, GlobalSettings
from profiles.permissions import IsStaffOrAdmin
from users.permissions import IsAdminUser

from ...models import Appointment
from ...serializers import AppointmentCancelSerializer, AppointmentListSerializer
from ...services import AppointmentService, WaitlistService
from finances.payments import PaymentService

logger = logging.getLogger(__name__)


class AppointmentAdminActionsMixin:
    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin], url_path='complete_final_payment')
    @transaction.atomic
    def complete_final_payment(self, request, pk=None):
        """Completa el pago final de una cita."""
        appointment = self.get_object()
        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            return Response(
                {'error': 'Solo se pueden completar pagos finales de citas confirmadas, reagendadas o totalmente pagadas.'},
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
            Appointment.AppointmentStatus.PENDING_PAYMENT,
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            return Response(
                {'error': 'Solo se pueden cancelar citas pendientes, confirmadas, reagendadas o totalmente pagadas.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.outcome = Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN
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

        # Notificar al cliente sobre la cancelación
        if appointment.user:
            try:
                from notifications.services import NotificationService
                start_time_local = timezone.localtime(appointment.start_time)
                services = appointment.get_service_names()

                # Mensaje sobre créditos dependiendo de si hubo reembolso
                if mark_as_refunded:
                    credit_message = "Se han generado créditos en tu cuenta que puedes usar en tu próxima visita."
                else:
                    credit_message = "Si consideras que deberías recibir un reembolso, por favor contáctanos."

                NotificationService.send_notification(
                    user=appointment.user,
                    event_code="APPOINTMENT_CANCELLED_BY_ADMIN",
                    context={
                        "user_name": appointment.user.get_full_name() or appointment.user.first_name or "Cliente",
                        "services": services,
                        "start_date": start_time_local.strftime("%d de %B %Y"),
                        "credit_message": credit_message,
                    },
                    priority="high"
                )
            except Exception:
                logger.exception("Error enviando notificación de cancelación por admin para cita %s", appointment.id)

        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin])
    def mark_as_no_show(self, request, pk=None):
        """Marca una cita como 'No Asistió'."""
        appointment = self.get_object()
        if appointment.status not in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            return Response(
                {'error': 'Solo las citas confirmadas, reagendadas o totalmente pagadas pueden ser marcadas como "No Asistió".'},
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

        # Cancelar pagos pendientes para evitar bloqueo por deuda
        PaymentService.cancel_pending_payments_for_appointment(appointment)

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

        list_serializer = AppointmentListSerializer(appointment, context={'request': request})
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrAdmin], url_path='receive-advance-in-person')
    @transaction.atomic
    def receive_advance_in_person(self, request, pk=None):
        """
        Registra un anticipo recibido en persona.

        POST /api/appointments/{id}/receive-advance-in-person/

        Request body:
        {
            "amount": 50000,
            "notes": "Cliente fiel, pagará el resto después" (optional)
        }

        La cita se confirma inmediatamente sin importar si el monto
        es menor al anticipo requerido (para clientes fieles).

        Response:
        {
            "appointment": {...},
            "payment": {...},
            "message": "..."
        }
        """
        from ...serializers import ReceiveAdvanceInPersonSerializer

        appointment = self.get_object()

        # Validar que la cita esté pendiente de pago
        if appointment.status != Appointment.AppointmentStatus.PENDING_PAYMENT:
            return Response(
                {'error': 'Solo se pueden recibir anticipos para citas pendientes de pago.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ReceiveAdvanceInPersonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount']
        notes = serializer.validated_data.get('notes', '')

        # Usar el método del servicio de pagos
        try:
            payment = PaymentService.create_cash_advance_payment(
                appointment=appointment,
                amount=amount,
                notes=notes
            )
        except ValidationError as exc:
            message = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

        # Actualizar la instancia de appointment después de que el servicio la modificó
        appointment.refresh_from_db()

        # Registrar en AuditLog
        AuditLog.objects.create(
            admin_user=request.user,
            target_user=appointment.user,
            target_appointment=appointment,
            action=AuditLog.Action.PAYMENT_RECEIVED_IN_PERSON,
            details=f"Admin '{request.user.first_name}' registró anticipo en efectivo de ${amount:,.0f}. Notas: {notes or 'N/A'}"
        )

        # Preparar respuesta
        appointment_serializer = AppointmentListSerializer(appointment, context={'request': request})

        return Response({
            'appointment': appointment_serializer.data,
            'payment': {
                'id': str(payment.id),
                'amount': str(payment.amount),
                'status': payment.status,
                'payment_method_type': payment.payment_method_type,
            },
            'message': f'Anticipo de ${amount:,.0f} registrado. Cita confirmada.',
        }, status=status.HTTP_200_OK)
