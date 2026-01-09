"""
Manejador de Estado de Gateway.

Contiene:
- apply_gateway_status: Procesa estado de Wompi y ejecuta side-effects
- poll_pending_payment: Consulta estado de pago pendiente
- send_payment_status_notification: Envía notificación WhatsApp
"""
import logging
from decimal import Decimal

from django.db import transaction

from core.utils.exceptions import BusinessLogicError
from finances.gateway import WompiGateway
from finances.models import Payment
from finances.services import DeveloperCommissionService
from finances.subscriptions import VipSubscriptionService
from finances.payments.utils import describe_payment_service, extract_decline_reason
from spa.models import Appointment


logger = logging.getLogger(__name__)


def apply_gateway_status(payment, gateway_status, transaction_payload=None):
    """
    Procesa el estado recibido de Wompi y ejecuta efectos secundarios.
    
    Maneja:
    - Actualización de estado del pago
    - Fulfillment de paquetes/VIP/órdenes
    - Actualización de estado de citas
    - Registro de comisión del desarrollador
    - Generación de cashback VIP
    - Notificaciones al usuario
    """
    # Import local para evitar ciclos
    from finances.payments.appointment_payments import calculate_outstanding_amount
    
    normalized = (gateway_status or "").upper()
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        previous_status = payment.status
        terminal_statuses = {
            Payment.PaymentStatus.APPROVED,
            Payment.PaymentStatus.DECLINED,
            Payment.PaymentStatus.TIMEOUT,
            Payment.PaymentStatus.ERROR,
            Payment.PaymentStatus.PAID_WITH_CREDIT,
            Payment.PaymentStatus.CANCELLED,
        }
        # Idempotencia: si ya está en estado terminal, no reprocesar.
        if previous_status in terminal_statuses:
            return payment.status

        if transaction_payload is not None:
            payment.raw_response = transaction_payload
        if normalized == 'APPROVED':
            if transaction_payload:
                payment.transaction_id = transaction_payload.get(
                    "id", payment.transaction_id)
            payment.status = Payment.PaymentStatus.APPROVED
            payment.save(update_fields=[
                         'status', 'transaction_id', 'raw_response', 'updated_at'])
            if payment.payment_type == Payment.PaymentType.PACKAGE:
                # Import lazy para evitar ciclo circular
                from spa.services.vouchers import PackagePurchaseService
                PackagePurchaseService.fulfill_purchase(payment)
            elif payment.payment_type == Payment.PaymentType.ADVANCE and payment.appointment:
                # Check if this payment covers the full amount
                outstanding = calculate_outstanding_amount(payment.appointment)

                if outstanding <= Decimal('0'):
                    # Fully paid with advance payment
                    payment.appointment.status = Appointment.AppointmentStatus.FULLY_PAID
                else:
                    # Only advance paid
                    payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                payment.appointment.save(
                    update_fields=['status', 'updated_at'])
            elif payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION:
                VipSubscriptionService.fulfill_subscription(payment)
            elif (
                payment.payment_type == Payment.PaymentType.FINAL
                and payment.appointment
            ):
                # Check if final payment covers everything
                outstanding = calculate_outstanding_amount(payment.appointment)

                if outstanding <= Decimal('0'):
                    # Fully paid
                    if payment.appointment.status == Appointment.AppointmentStatus.COMPLETED:
                        # If service already completed, keep as COMPLETED
                        pass
                    else:
                        # Fully paid but service pending
                        payment.appointment.status = Appointment.AppointmentStatus.FULLY_PAID
                else:
                    # Partial final payment - keep as CONFIRMED
                    # (outstanding_balance will show remaining debt)
                    if payment.appointment.status != Appointment.AppointmentStatus.COMPLETED:
                        payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                payment.appointment.save(
                    update_fields=['status', 'updated_at'])
            elif (
                payment.payment_type == Payment.PaymentType.ORDER
                and payment.order
            ):
                try:
                    from marketplace.services import OrderService  # import local para evitar ciclos
                    OrderService.confirm_payment(payment.order)
                except BusinessLogicError as exc:
                    logger.error("No se pudo confirmar la orden %s: %s", payment.order_id, exc)
            if payment.payment_type in (
                Payment.PaymentType.ADVANCE,
                Payment.PaymentType.FINAL,
                Payment.PaymentType.PACKAGE,
                Payment.PaymentType.VIP_SUBSCRIPTION,
                Payment.PaymentType.ORDER,
            ):
                DeveloperCommissionService.handle_successful_payment(payment)
                
                # Generar Cashback VIP (si aplica)
                try:
                    from finances.services.cashback import CashbackService
                    CashbackService.process_cashback(payment)
                except Exception as e:
                    logger.error("Error generating cashback for payment %s: %s", payment.id, e)

        elif normalized in ('DECLINED', 'VOIDED'):
            payment.status = Payment.PaymentStatus.DECLINED
            payment.save(update_fields=[
                         'status', 'raw_response', 'updated_at'])
        elif normalized == 'PENDING':
            payment.status = Payment.PaymentStatus.PENDING
            payment.save(update_fields=[
                         'status', 'raw_response', 'updated_at'])
        else:
            payment.status = Payment.PaymentStatus.ERROR
            payment.save(update_fields=[
                         'status', 'raw_response', 'updated_at'])
    
    send_payment_status_notification(
        payment=payment,
        new_status=payment.status,
        previous_status=previous_status,
        transaction_payload=transaction_payload
    )

    return payment.status


def poll_pending_payment(payment, timeout_minutes=30):
    """Consulta estado de un pago pendiente en Wompi."""
    if payment.status != Payment.PaymentStatus.PENDING:
        return False
    if not payment.transaction_id:
        payment.status = Payment.PaymentStatus.TIMEOUT
        payment.save(update_fields=['status', 'updated_at'])
        return False
    
    client = WompiGateway()
    tx = client.fetch_transaction(payment.transaction_id)
    
    if not tx:
        payment.status = Payment.PaymentStatus.TIMEOUT
        payment.save(update_fields=['status', 'updated_at'])
        return False
        
    transaction_data = tx.get('data') or tx
    transaction_status = transaction_data.get('status')
    if not transaction_status:
        payment.status = Payment.PaymentStatus.TIMEOUT
        payment.save(update_fields=['status', 'updated_at'])
        return False
    apply_gateway_status(
        payment, transaction_status, transaction_data)
    return True


def send_payment_status_notification(*, payment, new_status, previous_status, transaction_payload):
    """Envía notificación de estado de pago al usuario."""
    if new_status not in (
        Payment.PaymentStatus.APPROVED,
        Payment.PaymentStatus.DECLINED,
        Payment.PaymentStatus.ERROR,
    ):
        return
    if previous_status == new_status:
        return
    user = getattr(payment, "user", None)
    phone = getattr(user, "phone_number", None)
    if not user or not phone:
        return
    reference = None
    if isinstance(transaction_payload, dict):
        reference = transaction_payload.get(
            "id") or transaction_payload.get("reference")
    reference = reference or payment.transaction_id
    amount = payment.amount or Decimal('0')
    amount_str = f"{amount:,.2f}"
    display_name = user.get_full_name() if hasattr(
        user, "get_full_name") else (user.first_name or "")
    display_name = display_name or user.email or "Cliente"
    # Refactor: Use NotificationService instead of direct send_mail
    try:
        from notifications.services import NotificationService
    except ImportError:
        logger.warning("NotificationService not found, skipping notification.")
        return

    event_code = None
    if new_status == Payment.PaymentStatus.APPROVED:
        event_code = "PAYMENT_STATUS_APPROVED"
    elif new_status == Payment.PaymentStatus.DECLINED:
        event_code = "PAYMENT_STATUS_DECLINED"
    elif new_status == Payment.PaymentStatus.ERROR:
        event_code = "PAYMENT_STATUS_ERROR"
    
    if not event_code:
        return

    base_context = {
        "user_name": display_name,
        "amount": amount_str,
        "reference": reference or "N/A",
    }

    service_description = describe_payment_service(payment)
    if event_code == "PAYMENT_STATUS_APPROVED":
        context = {
            **base_context,
            "service": service_description,
        }
    elif event_code == "PAYMENT_STATUS_DECLINED":
        context = {
            **base_context,
            "decline_reason": extract_decline_reason(transaction_payload),
        }
    else:
        context = base_context

    try:
        NotificationService.send_notification(
            user=user,
            event_code=event_code,
            context=context,
            priority="high"
        )
    except Exception:
        logger.exception(
            "No se pudo enviar la notificación del pago %s con estado %s",
            payment.id,
            new_status,
        )
