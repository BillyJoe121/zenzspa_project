"""
Handler de pago en efectivo para creación de citas por admin.
"""
import logging

from django.utils import timezone

from finances.payments import PaymentService

from ...models import Appointment

logger = logging.getLogger(__name__)


def handle_admin_create_cash(*, appointment, client, validated_data, send_whatsapp):
    payment = None
    payment_link = None
    whatsapp_sent = False
    voucher_used = None

    # Pago en efectivo - registrar transacción inmediatamente
    logger.info(f"🔵 INICIANDO FLUJO DE PAGO EN EFECTIVO para cliente {client.id}")

    from finances.models import Payment
    from decimal import Decimal

    cash_amount = Decimal(str(validated_data.get('cash_amount', 0)))
    logger.info(f"🔵 cash_amount recibido: ${cash_amount}")

    # Crear el pago de anticipo
    payment_service = PaymentService(client)
    payment = payment_service.create_advance_payment_for_appointment(appointment)

    # Registrar el pago en efectivo recibido
    try:
        # ✅ ACTUALIZAR payment.amount con el monto REAL recibido
        payment.amount = cash_amount
        payment.payment_method_type = 'CASH'

        # Determinar estado del pago y de la cita según el monto recibido
        if cash_amount >= appointment.price_at_purchase:
            # Pago completo - cubrió todo el servicio
            payment.status = Payment.PaymentStatus.APPROVED
            appointment.status = Appointment.AppointmentStatus.FULLY_PAID
            payment_status_msg = "completo (totalmente pagado)"
            logger.info(f"✅ Pago completo: ${cash_amount} >= ${appointment.price_at_purchase}")

        elif cash_amount > Decimal('0'):
            # Pago parcial pero suficiente para confirmar
            payment.status = Payment.PaymentStatus.APPROVED
            appointment.status = Appointment.AppointmentStatus.CONFIRMED
            payment_status_msg = "parcial (cita confirmada)"
            logger.info(f"✅ Pago parcial: ${cash_amount} (confirmada con saldo pendiente)")

        else:
            # Sin pago - la cita queda pendiente
            payment.status = Payment.PaymentStatus.PENDING
            appointment.status = Appointment.AppointmentStatus.PENDING_PAYMENT
            payment_status_msg = "sin pago (pendiente)"
            logger.warning(f"⚠️ Sin pago en efectivo, cita pendiente")

        # ✅ Guardar con amount actualizado
        payment.save(update_fields=['amount', 'status', 'payment_method_type', 'updated_at'])
        appointment.save(update_fields=['status', 'updated_at'])

        logger.info(
            "Pago en efectivo registrado para cita %s: $%s (%s)",
            appointment.id,
            cash_amount,
            payment_status_msg
        )

        # 🔥 IMPORTANTE: Registrar comisión del desarrollador si el pago fue aprobado
        if payment.status == Payment.PaymentStatus.APPROVED:
            from finances.services import DeveloperCommissionService
            try:
                ledger = DeveloperCommissionService.register_commission(payment)
                if ledger:
                    logger.info(
                        "✅ Comisión registrada para pago en efectivo %s: $%s",
                        payment.id,
                        ledger.amount
                    )
                    # Evaluar si es momento de pagar al desarrollador
                    DeveloperCommissionService.evaluate_payout()
            except Exception as exc:
                logger.exception(
                    "Error registrando comisión para pago en efectivo %s: %s",
                    payment.id,
                    exc
                )

    except Exception as e:
        logger.exception(
            "Error registrando pago en efectivo para cita %s: %s",
            appointment.id,
            str(e)
        )
        # Continuar con el flujo, el pago quedará pendiente

    # Notificación según estado del pago
    if send_whatsapp and client.phone_number:
        try:
            from notifications.services import NotificationService
            service_names = ", ".join([s.name for s in validated_data['services']])
            start_time_local = timezone.localtime(appointment.start_time)

            # Usar el mismo template para citas confirmadas
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
                "Error enviando WhatsApp de pago en efectivo para cita %s: %s",
                appointment.id,
                str(e)
            )

    return payment, payment_link, whatsapp_sent, voucher_used
