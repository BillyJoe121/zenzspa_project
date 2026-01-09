"""
Pagos de Citas - Funciones base.

Contiene:
- calculate_outstanding_amount
- create_tip_payment
- create_final_payment
- create_cash_advance_payment
- create_advance_payment_for_appointment (método de instancia)
"""
import logging
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import GlobalSettings
from finances.models import ClientCredit, Payment, PaymentCreditUsage
from finances.services import DeveloperCommissionService
from spa.models import Appointment


logger = logging.getLogger(__name__)


def calculate_outstanding_amount(appointment: Appointment) -> Decimal:
    """Calcula el saldo pendiente de una cita."""
    total_paid = Decimal('0')
    relevant_statuses = [
        Payment.PaymentStatus.APPROVED,
        Payment.PaymentStatus.PAID_WITH_CREDIT,
    ]
    relevant_types = [
        Payment.PaymentType.ADVANCE,
        Payment.PaymentType.FINAL,
    ]
    for payment in appointment.payments.filter(
        payment_type__in=relevant_types,
        status__in=relevant_statuses,
    ):
        total_paid += payment.amount or Decimal('0')
    outstanding = (
        appointment.price_at_purchase or Decimal('0')) - total_paid
    if outstanding <= Decimal('0'):
        return Decimal('0')
    return outstanding


@transaction.atomic
def create_tip_payment(appointment: Appointment, user, amount) -> Payment:
    """Crea un pago de propina para una cita completada."""
    if appointment.status not in [
        Appointment.AppointmentStatus.COMPLETED,
        Appointment.AppointmentStatus.CONFIRMED,
        Appointment.AppointmentStatus.FULLY_PAID,
    ]:
        raise ValidationError(
            "Solo se pueden registrar propinas para citas completadas o confirmadas.")
    return Payment.objects.create(
        user=user,
        appointment=appointment,
        amount=amount,
        payment_type=Payment.PaymentType.TIP,
        status=Payment.PaymentStatus.APPROVED,
    )


@transaction.atomic
def create_final_payment(appointment: Appointment, user):
    """
    Crea pago final para completar el saldo de una cita.
    
    Retorna: (Payment, outstanding_amount)
    """
    outstanding = calculate_outstanding_amount(appointment)
    payment = None
    if outstanding > Decimal('0'):
        payment = Payment.objects.create(
            user=user,
            appointment=appointment,
            amount=outstanding,
            payment_type=Payment.PaymentType.FINAL,
            status=Payment.PaymentStatus.APPROVED,
        )
        DeveloperCommissionService.handle_successful_payment(payment)
        
        # Generar Cashback VIP para pago final (efectivo/transferencia manual)
        try:
            from finances.services.cashback import CashbackService
            CashbackService.process_cashback(payment)
        except Exception as e:
            logger.error("Error generating cashback for manual final payment %s: %s", payment.id, e)


        # Recalculate outstanding to determine new status
        outstanding_after = calculate_outstanding_amount(appointment)

        if outstanding_after <= Decimal('0'):
            appointment.status = Appointment.AppointmentStatus.FULLY_PAID
        else:
            appointment.status = Appointment.AppointmentStatus.CONFIRMED
        appointment.save(update_fields=['status', 'updated_at'])
    return payment, outstanding


@transaction.atomic
def create_cash_advance_payment(appointment: Appointment, amount: Decimal, notes: str = "") -> Payment:
    """
    Crea un registro de pago en efectivo recibido en persona para una cita.
    
    Este método:
    - Crea un Payment con status APPROVED y payment_method_type CASH
    - Cambia el estado de la cita a CONFIRMED (sin importar el monto)
    - Registra las notas del admin
    
    Args:
        appointment: Cita para la que se recibe el anticipo
        amount: Monto recibido en persona
        notes: Notas opcionales del admin
        
    Returns:
        Payment: El registro de pago creado
        
    Raises:
        ValidationError: Si la cita no está en estado PENDING_PAYMENT
    """
    if appointment.status != Appointment.AppointmentStatus.PENDING_PAYMENT:
        raise ValidationError(
            "Solo se pueden recibir anticipos para citas pendientes de pago."
        )
    
    reference = f"CASH-{str(appointment.id)[-12:]}-{uuid.uuid4().hex[:4]}"
    
    payment = Payment.objects.create(
        user=appointment.user,
        appointment=appointment,
        amount=amount,
        payment_type=Payment.PaymentType.ADVANCE,
        status=Payment.PaymentStatus.APPROVED,
        payment_method_type="CASH",
        transaction_id=reference,
        payment_method_data={"notes": notes} if notes else {},
    )
    
    # Confirmar la cita inmediatamente
    appointment.status = Appointment.AppointmentStatus.CONFIRMED
    appointment.save(update_fields=['status', 'updated_at'])
    
    # Registrar comisión del desarrollador
    DeveloperCommissionService.handle_successful_payment(payment)
    
    logger.info(
        "Anticipo en efectivo registrado: cita=%s, monto=%s, payment=%s",
        appointment.id,
        amount,
        payment.id,
    )

    return payment


class AppointmentPaymentHelper:
    """
    Helper para pagos de citas que requieren instancia con usuario.
    
    Uso:
        helper = AppointmentPaymentHelper(user)
        payment = helper.create_advance_payment_for_appointment(appointment)
    """
    
    def __init__(self, user):
        self.user = user

    @transaction.atomic
    def create_advance_payment_for_appointment(self, appointment: Appointment):
        """
        Crea el registro de pago de anticipo para una cita, aplicando
        el saldo a favor disponible del usuario si existe.
        """
        settings = GlobalSettings.load()
        price = appointment.price_at_purchase
        advance_percentage = Decimal(settings.advance_payment_percentage / 100)
        required_advance = price * advance_percentage

        # Buscar créditos válidos (disponibles, no expirados) del usuario
        available_credits = ClientCredit.objects.select_for_update().filter(
            user=self.user,
            status__in=[ClientCredit.CreditStatus.AVAILABLE,
                        ClientCredit.CreditStatus.PARTIALLY_USED],
            expires_at__gte=timezone.now().date()
        ).order_by('created_at')  # Usar los créditos más antiguos primero

        amount_to_pay = required_advance
        credit_movements: list[tuple[ClientCredit, Decimal]] = []

        for credit in available_credits:
            if amount_to_pay <= 0:
                break

            amount_from_this_credit = min(
                amount_to_pay, credit.remaining_amount)

            credit.remaining_amount -= amount_from_this_credit
            credit.save(update_fields=['remaining_amount', 'status', 'updated_at'])

            amount_to_pay -= amount_from_this_credit
            credit_movements.append((credit, amount_from_this_credit))

        # Crear el registro de pago
        payment = Payment.objects.create(
            user=self.user,
            appointment=appointment,
            amount=required_advance,
            payment_type=Payment.PaymentType.ADVANCE,
            used_credit=credit_movements[-1][0] if credit_movements else None
        )
        if credit_movements:
            PaymentCreditUsage.objects.bulk_create(
                [
                    PaymentCreditUsage(
                        payment=payment,
                        credit=credit,
                        amount=used_amount,
                    )
                    for credit, used_amount in credit_movements
                ]
            )

        if amount_to_pay <= 0:
            # El crédito cubrió todo el anticipo. La cita se confirma automáticamente.
            payment.status = Payment.PaymentStatus.PAID_WITH_CREDIT
            appointment.status = Appointment.AppointmentStatus.CONFIRMED
        else:
            # Queda un remanente por pagar. La cita queda pendiente.
            payment.status = Payment.PaymentStatus.PENDING
            # Actualizamos el monto del pago al remanente, para que la pasarela
            # solo cobre lo que falta.
            payment.amount = amount_to_pay

        payment.save()
        appointment.save(update_fields=['status'])

        return payment
