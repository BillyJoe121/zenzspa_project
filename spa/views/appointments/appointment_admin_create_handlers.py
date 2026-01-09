"""
Handlers de pago para creación de citas por admin.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from core.models import AuditLog, GlobalSettings
from finances.payments import PaymentService

from ...models import Appointment

logger = logging.getLogger(__name__)


def handle_admin_create_voucher(*, request, appointment, client, validated_data, send_whatsapp):
    payment = None
    payment_link = None
    whatsapp_sent = False
    voucher_used = None

    # Usar voucher para pagar
    voucher = validated_data['voucher']

    # Marcar voucher como usado
    voucher.status = voucher.VoucherStatus.USED
    voucher.save(update_fields=['status', 'updated_at'])

    # Crear pago con estado PAID_WITH_CREDIT (reutilizamos este estado para vouchers)
    from finances.models import Payment
    payment = Payment.objects.create(
        user=client,
        appointment=appointment,
        amount=appointment.price_at_purchase,
        status=Payment.PaymentStatus.PAID_WITH_CREDIT,
        payment_type=Payment.PaymentType.ADVANCE,
        payment_method_type='VOUCHER',
        transaction_id=f'VOUCHER-{voucher.code}'
    )

    # Confirmar la cita inmediatamente
    appointment.status = Appointment.AppointmentStatus.CONFIRMED
    appointment.save(update_fields=['status', 'updated_at'])

    voucher_used = {
        'id': str(voucher.id),
        'code': voucher.code,
        'service': voucher.service.name
    }

    # Enviar notificación de cita confirmada con voucher
    if send_whatsapp and client.phone_number:
        try:
            from notifications.services import NotificationService
            service_names = ", ".join([s.name for s in validated_data['services']])
            start_time_local = timezone.localtime(appointment.start_time)

            NotificationService.send_notification(
                user=client,
                event_code="ADMIN_APPOINTMENT_CONFIRMED",
                context={
                    "user_name": client.get_full_name() or client.first_name or "Cliente",
                    "services": service_names,
                    "start_date": start_time_local.strftime("%d de %B %Y"),
                    "start_time": start_time_local.strftime("%I:%M %p"),
                },
                priority="high"
            )
            whatsapp_sent = True
        except Exception as e:
            logger.exception(
                "Error enviando WhatsApp de confirmación con voucher para cita %s: %s",
                appointment.id,
                str(e)
            )

    # Registrar en AuditLog
    AuditLog.objects.create(
        admin_user=request.user,
        target_user=client,
        target_appointment=appointment,
        action=AuditLog.Action.VOUCHER_REDEEMED,
        details=f"Admin '{request.user.first_name}' usó voucher {voucher.code} para cita {appointment.id}"
    )

    return payment, payment_link, whatsapp_sent, voucher_used


def handle_admin_create_credit(*, appointment, client, validated_data, send_whatsapp):
    payment = None
    payment_link = None
    whatsapp_sent = False
    voucher_used = None

    # Intentar usar crédito disponible
    payment_service = PaymentService(client)
    payment = payment_service.create_advance_payment_for_appointment(appointment)

    # Si el crédito cubrió todo, confirmar cita
    if payment.status == payment.PaymentStatus.PAID_WITH_CREDIT:
        appointment.status = Appointment.AppointmentStatus.CONFIRMED
        appointment.save(update_fields=['status', 'updated_at'])

        # Notificación de cita confirmada con crédito
        if send_whatsapp and client.phone_number:
            try:
                from notifications.services import NotificationService
                service_names = ", ".join([s.name for s in validated_data['services']])
                start_time_local = timezone.localtime(appointment.start_time)

                NotificationService.send_notification(
                    user=client,
                    event_code="ADMIN_APPOINTMENT_CONFIRMED",
                    context={
                        "user_name": client.get_full_name() or client.first_name or "Cliente",
                        "services": service_names,
                        "start_date": start_time_local.strftime("%d de %B %Y"),
                        "start_time": start_time_local.strftime("%I:%M %p"),
                    },
                    priority="high"
                )
                whatsapp_sent = True
            except Exception as e:
                logger.exception(
                    "Error enviando WhatsApp de confirmación con crédito para cita %s: %s",
                    appointment.id,
                    str(e)
                )
    else:
        # Si no cubrió todo, generar link de pago por la diferencia
        payment_link = PaymentService.generate_checkout_url(payment)

        # Enviar notificación con link de pago
        if send_whatsapp and payment_link and client.phone_number:
            try:
                from notifications.services import NotificationService
                settings_obj = GlobalSettings.load()
                expiration_minutes = settings_obj.advance_expiration_minutes
                expiration_time = timezone.now() + timedelta(minutes=expiration_minutes)
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

    return payment, payment_link, whatsapp_sent, voucher_used


def handle_admin_create_payment_link(*, appointment, client, validated_data, send_whatsapp):
    payment = None
    payment_link = None
    whatsapp_sent = False
    voucher_used = None

    # Crear el pago de anticipo
    payment_service = PaymentService(client)
    payment = payment_service.create_advance_payment_for_appointment(appointment)

    # Generar link de pago si el anticipo no fue cubierto por crédito
    if payment.status != payment.PaymentStatus.PAID_WITH_CREDIT:
        payment_link = PaymentService.generate_checkout_url(payment)
    else:
        # Si el crédito cubrió todo, confirmar cita
        appointment.status = Appointment.AppointmentStatus.CONFIRMED
        appointment.save(update_fields=['status', 'updated_at'])

    # Enviar notificación WhatsApp con link de pago
    if send_whatsapp and payment_link and client.phone_number:
        try:
            from notifications.services import NotificationService
            settings_obj = GlobalSettings.load()
            expiration_minutes = settings_obj.advance_expiration_minutes
            expiration_time = timezone.now() + timedelta(minutes=expiration_minutes)
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

    return payment, payment_link, whatsapp_sent, voucher_used
