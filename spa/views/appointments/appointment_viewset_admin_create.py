"""
Creación de citas por admin/staff.
"""
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils.exceptions import BusinessLogicError
from core.models import AuditLog
from profiles.permissions import IsStaffOrAdmin
from users.models import CustomUser

from ...serializers import AppointmentListSerializer
from ...services import AppointmentService
from .appointment_admin_create_cash import handle_admin_create_cash
from .appointment_admin_create_handlers import (
    handle_admin_create_credit,
    handle_admin_create_payment_link,
    handle_admin_create_voucher,
)
from core.utils.decorators import idempotent_view

logger = logging.getLogger(__name__)


class AppointmentAdminCreateMixin:
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
            "payment_method": "VOUCHER|CREDIT|PAYMENT_LINK|CASH" (default: PAYMENT_LINK),
            "voucher_id": "uuid" (requerido si payment_method=VOUCHER),
            "send_whatsapp": true/false (default: true)
        }

        Response:
        {
            "appointment": {...},
            "payment": {...},
            "payment_link": "https://checkout.wompi.co/..." (si aplica),
            "whatsapp_sent": true/false,
            "voucher_used": {...} (si aplica)
        }
        """
        from ...serializers import AdminAppointmentCreateSerializer

        serializer = AdminAppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # Obtener cliente
        client = CustomUser.objects.get(id=validated_data['client_id'])
        payment_method = validated_data.get('payment_method', 'PAYMENT_LINK')

        logger.info(
            "[ADMIN_CREATE_APPOINTMENT] Admin %s creando cita para cliente %s. Método de pago: %s",
            request.user.phone_number,
            client.phone_number,
            payment_method
        )

        try:
            # Crear la cita usando el servicio existente
            appointment_service = AppointmentService(
                user=client,
                services=validated_data['services'],
                staff_member=validated_data.get('staff_member'),
                start_time=validated_data['start_time']
            )
            appointment = appointment_service.create_appointment_with_lock()

            logger.info(
                "[ADMIN_CREATE_APPOINTMENT] Cita %s creada exitosamente para cliente %s",
                appointment.id,
                client.phone_number
            )
        except BusinessLogicError as exc:
            logger.error(
                "[ADMIN_CREATE_APPOINTMENT] Error BusinessLogicError al crear cita para %s: %s",
                client.phone_number,
                str(exc)
            )
            raise exc
        except ValueError as e:
            logger.error(
                "[ADMIN_CREATE_APPOINTMENT] ValueError al crear cita para %s: %s",
                client.phone_number,
                str(e)
            )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Variables para la respuesta
        payment = None
        payment_link = None
        whatsapp_sent = False
        voucher_used = None
        send_whatsapp = validated_data.get('send_whatsapp', True)

        # Procesar según método de pago
        if payment_method == 'VOUCHER':
            payment, payment_link, whatsapp_sent, voucher_used = handle_admin_create_voucher(
                request=request,
                appointment=appointment,
                client=client,
                validated_data=validated_data,
                send_whatsapp=send_whatsapp,
            )
        elif payment_method == 'CREDIT':
            payment, payment_link, whatsapp_sent, voucher_used = handle_admin_create_credit(
                appointment=appointment,
                client=client,
                validated_data=validated_data,
                send_whatsapp=send_whatsapp,
            )
        elif payment_method == 'CASH':
            payment, payment_link, whatsapp_sent, voucher_used = handle_admin_create_cash(
                appointment=appointment,
                client=client,
                validated_data=validated_data,
                send_whatsapp=send_whatsapp,
            )
        else:  # PAYMENT_LINK (default)
            payment, payment_link, whatsapp_sent, voucher_used = handle_admin_create_payment_link(
                appointment=appointment,
                client=client,
                validated_data=validated_data,
                send_whatsapp=send_whatsapp,
            )

        # Registrar en AuditLog
        AuditLog.objects.create(
            admin_user=request.user,
            target_user=client,
            target_appointment=appointment,
            action=AuditLog.Action.APPOINTMENT_CREATED_BY_ADMIN,
            details=f"Admin '{request.user.first_name}' creó cita para cliente {client.phone_number}. Método: {payment_method}. WhatsApp enviado: {whatsapp_sent}."
        )

        # Preparar respuesta
        appointment_serializer = AppointmentListSerializer(appointment, context={'request': request})

        response_data = {
            'appointment': appointment_serializer.data,
            'payment_method': payment_method,
            'whatsapp_sent': whatsapp_sent,
        }

        if payment:
            response_data['payment'] = {
                'id': str(payment.id),
                'amount': str(payment.amount),
                'status': payment.status,
                'payment_type': payment.payment_type,
            }

        if payment_link:
            response_data['payment_link'] = payment_link

        if voucher_used:
            response_data['voucher_used'] = voucher_used

        return Response(response_data, status=status.HTTP_201_CREATED)
