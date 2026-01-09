"""
Iniciación de Pago de Citas.

Contiene:
- initiate_appointment_payment: Flujo completo de inicio de pago para citas
"""
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from core.models import GlobalSettings
from finances.gateway import build_integrity_signature
from finances.models import Payment, PaymentCreditUsage
from finances.services import DeveloperCommissionService
from finances.payments.credits import apply_credits_to_payment, preview_credits_application
from finances.payments.appointment_payments import calculate_outstanding_amount
from spa.models import Appointment


logger = logging.getLogger(__name__)


def initiate_appointment_payment(
    appointment: Appointment,
    user,
    payment_type: str = 'deposit',
    use_credits: bool = False,
    confirm: bool = False
) -> dict:
    """
    Inicia el flujo de pago para una cita.
    
    Este método encapsula toda la lógica de negocio para:
    - Calcular el monto a pagar según el tipo de pago
    - Generar preview de créditos (modo preview)
    - Aplicar créditos y crear pagos (modo confirm)
    - Generar payload para Wompi si hay remanente

    Args:
        appointment: Cita para la cual se inicia el pago
        user: Usuario que realiza el pago
        payment_type: 'deposit', 'full', o 'balance'
        use_credits: Si debe aplicar/mostrar créditos
        confirm: False=preview (solo lectura), True=confirmar (modifica DB)

    Returns:
        dict con:
            - En modo preview: datos del preview
            - En modo confirm con crédito total: status='paid_with_credit'
            - En modo confirm con Wompi: payload para el widget

    Raises:
        ValueError: Si el estado de la cita no permite pagos
    """
    total_price = appointment.price_at_purchase
    outstanding = calculate_outstanding_amount(appointment)

    # Determinar el monto y tipo de pago según el estado de la cita
    if appointment.status == Appointment.AppointmentStatus.PENDING_PAYMENT:
        if payment_type == 'full':
            amount = total_price
            payment_type_enum = Payment.PaymentType.FINAL
        elif payment_type == 'balance':
            if outstanding <= Decimal('0'):
                raise ValueError("Esta cita no tiene saldo pendiente por pagar.")
            amount = outstanding
            payment_type_enum = Payment.PaymentType.FINAL
        else:  # deposit (default)
            global_settings = GlobalSettings.load()
            advance_percentage = Decimal(global_settings.advance_payment_percentage / 100)

            logger.info(
                "Consultando pago de cita: appointment_id=%s, user=%s, price=%s, advance_pct=%s, confirm=%s",
                appointment.id, user.id, total_price, advance_percentage, confirm
            )

            amount = total_price * advance_percentage
            payment_type_enum = Payment.PaymentType.ADVANCE

    elif appointment.status in [
        Appointment.AppointmentStatus.CONFIRMED,
        Appointment.AppointmentStatus.RESCHEDULED,
        Appointment.AppointmentStatus.FULLY_PAID,
    ]:
        if outstanding <= Decimal('0'):
            raise ValueError("Esta cita no tiene saldo pendiente por pagar.")
        amount = outstanding
        payment_type_enum = Payment.PaymentType.FINAL

    else:
        raise ValueError(
            f"No se puede iniciar pago para citas con estado '{appointment.get_status_display()}'."
        )

    # ========================================
    # MODO PREVIEW (sin confirm=true)
    # ========================================
    if not confirm:
        preview_data = {
            'mode': 'preview',
            'appointmentId': str(appointment.id),
            'appointmentStatus': appointment.status,
            'paymentType': payment_type_enum,
            'totalPrice': str(total_price),
            'selectedAmount': str(amount),
            'outstandingBalance': str(outstanding),
        }
        
        if use_credits:
            credit_preview = preview_credits_application(user, amount)
            preview_data['creditPreview'] = {
                'availableCredits': str(credit_preview['available_credits']),
                'creditsToApply': str(credit_preview['credits_to_apply']),
                'amountAfterCredits': str(credit_preview['amount_remaining']),
                'fullyCoveredByCredits': credit_preview['fully_covered'],
            }
        
        return preview_data

    # ========================================
    # MODO CONFIRMACIÓN (con confirm=true)
    # ========================================
    with transaction.atomic():
        credits_applied = Decimal('0')
        credit_movements = []

        if use_credits:
            credit_result = apply_credits_to_payment(user, amount)
            credits_applied = credit_result.credits_applied
            credit_movements = credit_result.credit_movements
            amount_to_pay = credit_result.amount_remaining

            logger.info(
                "Créditos aplicados a cita (CONFIRM): appointment_id=%s, user=%s, credits_used=%s, remaining=%s",
                appointment.id, user.id, credits_applied, amount_to_pay
            )

            # Si los créditos cubrieron TODO el monto
            if credit_result.fully_covered:
                reference = f"APPT-CREDIT-{appointment.id}-{uuid.uuid4().hex[:8]}"

                payment = Payment.objects.create(
                    user=user,
                    appointment=appointment,
                    amount=credits_applied,
                    payment_type=payment_type_enum,
                    status=Payment.PaymentStatus.PAID_WITH_CREDIT,
                    transaction_id=reference,
                    used_credit=credit_movements[0][0] if credit_movements else None
                )

                PaymentCreditUsage.objects.bulk_create([
                    PaymentCreditUsage(
                        payment=payment,
                        credit=credit,
                        amount=used_amount
                    )
                    for credit, used_amount in credit_movements
                ])

                new_outstanding = calculate_outstanding_amount(appointment)
                if new_outstanding <= Decimal('0'):
                    appointment.status = Appointment.AppointmentStatus.FULLY_PAID
                else:
                    appointment.status = Appointment.AppointmentStatus.CONFIRMED

                appointment.save(update_fields=['status', 'updated_at'])
                DeveloperCommissionService.handle_successful_payment(payment)

                return {
                    'status': 'paid_with_credit',
                    'paymentId': str(payment.id),
                    'credits_used': str(credits_applied),
                    'amount_paid': '0',
                    'appointmentStatus': appointment.status,
                    'paymentType': payment_type_enum
                }

            # Créditos parciales
            if credits_applied > 0:
                credit_payment = Payment.objects.create(
                    user=user,
                    appointment=appointment,
                    amount=credits_applied,
                    payment_type=payment_type_enum,
                    status=Payment.PaymentStatus.PAID_WITH_CREDIT,
                    transaction_id=f"APPT-CREDIT-{appointment.id}-{uuid.uuid4().hex[:8]}",
                    used_credit=credit_movements[0][0] if credit_movements else None
                )

                PaymentCreditUsage.objects.bulk_create([
                    PaymentCreditUsage(
                        payment=credit_payment,
                        credit=credit,
                        amount=used_amount
                    )
                    for credit, used_amount in credit_movements
                ])

                DeveloperCommissionService.handle_successful_payment(credit_payment)

                logger.info(
                    "Pago parcial con crédito creado: appointment_id=%s, payment_id=%s, amount=%s",
                    appointment.id, credit_payment.id, credits_applied
                )

            amount = amount_to_pay
        else:
            amount_to_pay = amount

        # Buscar o crear el pago pendiente
        try:
            payment = appointment.payments.get(
                status=Payment.PaymentStatus.PENDING,
                payment_type=payment_type_enum
            )
            payment.amount = amount
            payment.save()
        except Payment.DoesNotExist:
            payment = Payment.objects.create(
                user=user,
                appointment=appointment,
                amount=amount,
                payment_type=payment_type_enum,
                status=Payment.PaymentStatus.PENDING
            )

        amount_in_cents = int(payment.amount * 100)
        suffix = uuid.uuid4().hex[:6]
        reference = f"PAY-{str(payment.id)[-10:]}-{suffix}"
        payment.transaction_id = reference
        payment.save()

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        redirect_url = settings.WOMPI_REDIRECT_URL
        if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
            redirect_url = 'about:blank'
            logger.warning(
                "[DEVELOPMENT] Usando 'about:blank' como redirectUrl porque "
                "WOMPI_REDIRECT_URL contiene localhost: %s", settings.WOMPI_REDIRECT_URL
            )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,
            'redirectUrl': redirect_url,
            'paymentId': str(payment.id),
            'paymentType': payment_type_enum,
            'appointmentStatus': appointment.status,
        }

        if use_credits and credits_applied > 0:
            payment_data['credits_used'] = str(credits_applied)
            payment_data['original_amount'] = str(amount + credits_applied)
            payment_data['status'] = 'partial_credit'

        return payment_data
