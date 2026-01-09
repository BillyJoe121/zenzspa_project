from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.utils.exceptions import BusinessLogicError
from core.models import GlobalSettings, IdempotencyKey
from finances.models import ClientCredit, Payment, WebhookEvent
from marketplace.models import Order

from .shared import logger, payment_failures


@transaction.atomic
def process_transaction_update(service):
    """
    Procesa un evento 'transaction.updated'.
    Es idempotente y seguro.
    """
    # Importación local para evitar ciclos con PaymentService
    from ..payments import PaymentService

    try:
        service._validate_signature()

        transaction_data = service.data.get("transaction", {})
        reference = transaction_data.get("reference")
        transaction_status = transaction_data.get("status")

        if not reference or not transaction_status:
            logger.error(
                "[PAYMENT-ALERT] Webhook Error: Referencia o estado ausentes (event=%s)", service.event_type)
            raise ValueError(
                "Referencia o estado de la transacción ausentes en el webhook.")

        # Idempotencia por referencia
        idem_key, _ = IdempotencyKey.objects.get_or_create(
            key=f"wompi:{reference}",
            defaults={
                "endpoint": "webhook:transaction.updated",
                "status": IdempotencyKey.Status.PENDING,
            },
        )

        try:
            payment = Payment.objects.select_for_update().get(
                transaction_id=reference,
                status=Payment.PaymentStatus.PENDING,
            )
        except Payment.DoesNotExist:
            try:
                order = Order.objects.select_for_update().get(wompi_transaction_id=reference)
            except Order.DoesNotExist:
                service._update_event_status(
                    WebhookEvent.Status.IGNORED, "Pago u orden no encontrados.")
                logger.error(
                    "[PAYMENT-ALERT] Webhook Error: Pago u orden no encontrados (reference=%s)", reference)
                return {"status": "already_processed_or_invalid"}

            amount_in_cents = transaction_data.get("amount_in_cents")
            expected_cents = int(
                (order.total_amount or Decimal('0')) * Decimal('100'))

            payment_record = order.payments.filter(transaction_id=reference).first()

            if transaction_status == 'APPROVED':
                if amount_in_cents is None or int(amount_in_cents) != expected_cents:
                    order.status = Order.OrderStatus.FRAUD_ALERT
                    order.fraud_reason = "Monto pagado no coincide con el total."
            try:
                order = Order.objects.select_for_update().get(wompi_transaction_id=reference)
            except Order.DoesNotExist:
                service._update_event_status(
                    WebhookEvent.Status.IGNORED, "Pago u orden no encontrados.")
                logger.error(
                    "[PAYMENT-ALERT] Webhook Error: Pago u orden no encontrados (reference=%s)", reference)
                return {"status": "already_processed_or_invalid"}

            amount_in_cents = transaction_data.get("amount_in_cents")
            expected_cents = int(
                (order.total_amount or Decimal('0')) * Decimal('100'))

            payment_record = order.payments.filter(transaction_id=reference).first()

            if transaction_status == 'APPROVED':
                if amount_in_cents is None or int(amount_in_cents) != expected_cents:
                    order.status = Order.OrderStatus.FRAUD_ALERT
                    order.fraud_reason = "Monto pagado no coincide con el total."
                    order.save(update_fields=[
                               'status', 'fraud_reason', 'updated_at'])
                    service._update_event_status(
                        WebhookEvent.Status.FAILED, "Diferencia en montos detectada.")
                    logger.error(
                        "[PAYMENT-ALERT] Webhook Error: Diferencia en montos detectada (reference=%s expected=%s got=%s)",
                        reference,
                        expected_cents,
                        amount_in_cents,
                    )
                    payment_failures.labels(reason="amount_mismatch", gateway="wompi").inc()
                    return {"status": "fraud_alert"}
                order.wompi_transaction_id = transaction_data.get(
                    "id", order.wompi_transaction_id)
                order.save(update_fields=[
                           'wompi_transaction_id', 'updated_at'])
                from marketplace.services import OrderService
                try:
                    OrderService.confirm_payment(order)
                    if payment_record:
                        payment_record.status = Payment.PaymentStatus.APPROVED
                        payment_record.raw_response = transaction_data
                        payment_record.save(update_fields=['status', 'raw_response', 'updated_at'])
                        
                        # Trigger Cashback
                        try:
                            from finances.services.cashback import CashbackService
                            CashbackService.process_cashback(payment_record)
                        except Exception as e:
                            logger.error("Error generating cashback for payment %s: %s", payment_record.id, e)

                except BusinessLogicError as exc:
                    payload = exc.detail if isinstance(exc.detail, dict) else {}
                    code = payload.get("code")
                    if code == "MKT-STOCK-EXPIRED":
                        OrderService.release_reservation(
                            order,
                            reason="Reserva expirada sin stock disponible.",
                        )
                        settings_obj = GlobalSettings.load()
                        expires = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
                        credit = ClientCredit.objects.create(
                            user=order.user,
                            originating_payment=payment_record,
                            initial_amount=order.total_amount,
                            remaining_amount=order.total_amount,
                            status=ClientCredit.CreditStatus.AVAILABLE,
                            expires_at=expires,
                        )
                        if payment_record:
                            payment_record.status = Payment.PaymentStatus.APPROVED
                            payment_record.raw_response = transaction_data
                            payment_record.save(update_fields=['status', 'raw_response', 'updated_at'])
                        service._update_event_status(
                            WebhookEvent.Status.PROCESSED, "Orden convertida en crédito por falta de stock.")
                        logger.warning(
                            "Pago tardío convertido en crédito para la orden %s (crédito %s).",
                            order.id,
                            credit.id,
                        )
                        return {"status": "order_refunded_credit", "order_id": str(order.id)}
                    OrderService.transition_to(
                        order, Order.OrderStatus.FRAUD_ALERT)
                    OrderService.release_reservation(
                        order,
                        reason=str(exc),
                    )
                    service._update_event_status(
                        WebhookEvent.Status.FAILED, str(exc))
                    logger.error("[PAYMENT-ALERT] Webhook Error: %s", exc)
                    payment_failures.labels(reason="fraud_check_failed", gateway="wompi").inc()
                    return {"status": "fraud_alert"}
            else:
                from marketplace.services import OrderService
                OrderService.transition_to(
                    order, Order.OrderStatus.CANCELLED)
            service._update_event_status(WebhookEvent.Status.PROCESSED)
            return {"status": "order_processed", "order_id": str(order.id)}

        amount_in_cents = transaction_data.get("amount_in_cents")
        if amount_in_cents is not None and payment.amount is not None:
            expected_cents = int(payment.amount * 100)
            if int(amount_in_cents) != expected_cents:
                payment.status = Payment.PaymentStatus.ERROR
                payment.raw_response = transaction_data
                payment.save(update_fields=["status", "raw_response", "updated_at"])
                service._update_event_status(
                    WebhookEvent.Status.FAILED, "Diferencia en montos detectada en webhook."
                )
                logger.error(
                    "[PAYMENT-ALERT] Webhook Error: Diferencia en montos detectada (payment=%s expected=%s got=%s)",
                    payment.id,
                    expected_cents,
                    amount_in_cents,
                )
                payment_failures.labels(reason="amount_mismatch", gateway="wompi").inc()
                return {"status": "amount_mismatch"}

        PaymentService.apply_gateway_status(
            payment, transaction_status, transaction_data)
        service._update_event_status(WebhookEvent.Status.PROCESSED)
        idem_key.mark_completed(
            response_body={"payment_id": str(payment.id)},
            status_code=200,
        )
        return {"status": "processed_successfully", "payment_id": payment.id}
    except Exception as exc:
        service._update_event_status(WebhookEvent.Status.FAILED, str(exc))
        logger.error("[PAYMENT-ALERT] Webhook Error: %s",
                     exc, exc_info=True)
        payment_failures.labels(reason="unhandled_exception", gateway="wompi").inc()
        raise
