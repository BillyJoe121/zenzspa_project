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
from legal.models import LegalDocument, UserConsent
from legal.permissions import consent_required_permission

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

        start_time_local = timezone.localtime(appointment.start_time)
        notification_context = {
            "user_name": (
                appointment.user.get_full_name()
                or appointment.user.first_name
                or "Cliente"
            ),
            "start_date": start_time_local.strftime("%d de %B %Y"),
            "appointment_id": str(appointment.id),
            "start_time": appointment.start_time.isoformat(),
            "credit_amount": str(credit_generated),
        }
        if credit_generated > 0:
            try:
                from notifications.services import NotificationService
                NotificationService.send_notification(
                    user=appointment.user,
                    event_code="APPOINTMENT_NO_SHOW_CREDIT",
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

    @action(detail=False, methods=['post'], permission_classes=[IsStaffOrAdmin], url_path='admin-create')
    @idempotent_view(timeout=60)
    @transaction.atomic
    def admin_create_for_client(self, request):
        """
        Admin/Staff crea una cita en nombre de un cliente.
        
        POST /api/appointments/admin-create/
        
        Request body:
        {
            "client_id": "uuid",
            "service_ids": ["uuid", ...],
            "staff_member_id": "uuid" (optional),
            "start_time": "ISO datetime",
            "send_whatsapp": true/false (default: true)
        }
        
        Response:
        {
            "appointment": {...},
            "payment": {...}, 
            "payment_link": "https://checkout.wompi.co/...",
            "whatsapp_sent": true/false
        }
        """
        from ...serializers import AdminAppointmentCreateSerializer
        
        serializer = AdminAppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        
        # Obtener cliente
        client = CustomUser.objects.get(id=validated_data['client_id'])
        
        try:
            # Crear la cita usando el servicio existente
            appointment_service = AppointmentService(
                user=client,
                services=validated_data['services'],
                staff_member=validated_data.get('staff_member'),
                start_time=validated_data['start_time']
            )
            appointment = appointment_service.create_appointment_with_lock()
        except BusinessLogicError as exc:
            raise exc
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        # Crear el pago de anticipo
        payment_service = PaymentService(client)
        payment = payment_service.create_advance_payment_for_appointment(appointment)
        
        # Generar link de pago si el anticipo no fue cubierto por crédito
        payment_link = None
        if payment.status != payment.PaymentStatus.PAID_WITH_CREDIT:
            payment_link = PaymentService.generate_checkout_url(payment)
        
        # Enviar notificación WhatsApp con link de pago
        whatsapp_sent = False
        send_whatsapp = validated_data.get('send_whatsapp', True)
        
        if send_whatsapp and payment_link and client.phone_number:
            try:
                from notifications.services import NotificationService
                
                # Calcular tiempo de expiración
                settings_obj = GlobalSettings.load()
                expiration_minutes = settings_obj.advance_expiration_minutes
                expiration_time = timezone.now() + timedelta(minutes=expiration_minutes)
                
                # Obtener nombres de servicios
                service_names = ", ".join([s.name for s in validated_data['services']])
                
                NotificationService.send_notification(
                    user=client,
                    event_code="ADMIN_APPOINTMENT_PAYMENT_LINK",
                    context={
                        "user_name": client.get_full_name() or client.first_name or "Cliente",
                        "services": service_names,
                        "amount": f"${payment.amount:,.0f}",
                        "payment_url": payment_link,
                        "expiration_time": expiration_time.strftime("%I:%M %p"),
                    },
                    priority="high"
                )
                whatsapp_sent = True
            except Exception as e:
                logger.exception(
                    "Error enviando WhatsApp con link de pago para cita %s: %s",
                    appointment.id,
                    str(e)
                )
        
        # Registrar en AuditLog
        AuditLog.objects.create(
            admin_user=request.user,
            target_user=client,
            target_appointment=appointment,
            action=AuditLog.Action.APPOINTMENT_CREATED_BY_ADMIN,
            details=f"Admin '{request.user.first_name}' creó cita para cliente {client.phone_number}. WhatsApp enviado: {whatsapp_sent}."
        )
        
        # Preparar respuesta
        appointment_serializer = AppointmentListSerializer(appointment, context={'request': request})
        
        return Response({
            'appointment': appointment_serializer.data,
            'payment': {
                'id': str(payment.id),
                'amount': str(payment.amount),
                'status': payment.status,
                'payment_type': payment.payment_type,
            },
            'payment_link': payment_link,
            'whatsapp_sent': whatsapp_sent,
        }, status=status.HTTP_201_CREATED)

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

