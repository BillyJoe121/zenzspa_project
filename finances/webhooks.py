import hashlib
import logging
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from core.models import GlobalSettings
from finances.models import (
    ClientCredit,
    Payment,
    WebhookEvent,
)
from marketplace.models import Order

logger = logging.getLogger(__name__)


class WompiWebhookService:
    """
    Servicio para procesar y validar webhooks de Wompi.
    """

    def __init__(self, request_data, headers=None):
        if isinstance(request_data, dict):
            self.request_body = request_data
        else:
            try:
                self.request_body = dict(request_data)
            except Exception:
                self.request_body = {}
        self.data = self.request_body.get("data", {})
        self.event_type = self.request_body.get("event")
        self.sent_signature = self.request_body.get(
            "signature", {}).get("checksum")
        self.timestamp = self.request_body.get("timestamp")
        self.headers = headers or {}
        self.event_record = WebhookEvent.objects.create(
            payload=self.request_body,
            headers=dict(self.headers),
            event_type=self.event_type or "",
            status=WebhookEvent.Status.PROCESSED,
        )

    def _validate_signature(self):
        """
        Valida la firma del evento según el algoritmo oficial de Wompi.

        Algoritmo oficial:
        1. Extraer properties del signature object
        2. Obtener valores de data según properties
        3. Concatenar valores + timestamp + secret
        4. SHA256 y comparar con checksum

        Referencia: https://docs.wompi.co/docs/es/eventos#seguridad
        """
        if not all([self.data, self.timestamp]):
            logger.error(
                "[PAYMENT-ALERT] Webhook Error: Datos incompletos (event=%s)", self.event_type
            )
            raise ValueError("Datos del webhook incompletos.")

        signature_obj = self.request_body.get("signature", {})
        properties = signature_obj.get("properties", [])
        sent_checksum = signature_obj.get("checksum")

        if not sent_checksum or not properties:
            logger.error(
                "[PAYMENT-ALERT] Webhook Error: Firma o properties ausentes (event=%s)", self.event_type
            )
            raise ValueError("Firma del webhook incompleta.")

        # Paso 1: Concatenar valores según properties del evento
        # Ej: properties=["transaction.id", "transaction.status"] -> extraer esos valores
        values = []
        for prop_path in properties:
            # Navegar por el path: "transaction.id" -> data["transaction"]["id"]
            keys = prop_path.split(".")
            value = self.data

            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key, "")
                else:
                    value = ""
                    break

            values.append(str(value))

        concatenated = "".join(values)

        # Paso 2: Agregar timestamp
        concatenated += str(self.timestamp)

        # Paso 3: Agregar secreto de eventos
        event_secret = getattr(settings, "WOMPI_EVENT_SECRET", "")
        if not event_secret:
            logger.error("[PAYMENT-ALERT] WOMPI_EVENT_SECRET no configurado")
            raise ValueError("WOMPI_EVENT_SECRET no está configurado.")

        concatenated += event_secret

        # Paso 4: Calcular SHA256
        calculated_checksum = hashlib.sha256(concatenated.encode('utf-8')).hexdigest()

        # Paso 5: Comparar checksums (case-insensitive)
        if calculated_checksum.upper() != sent_checksum.upper():
            logger.error(
                "[PAYMENT-ALERT] Webhook Error: Firma inválida (event=%s). "
                "Calculado: %s, Recibido: %s, Properties: %s",
                self.event_type,
                calculated_checksum,
                sent_checksum,
                properties
            )
            raise ValueError("Firma del webhook inválida. La petición podría ser fraudulenta.")

        logger.info("[PAYMENT-SUCCESS] Webhook validado correctamente (event=%s)", self.event_type)

    def _update_event_status(self, status, error_message=None):
        self.event_record.status = status
        self.event_record.error_message = error_message or ""
        self.event_record.save(
            update_fields=['status', 'error_message', 'updated_at'])

    @transaction.atomic
    def process_transaction_update(self):
        """
        Procesa un evento 'transaction.updated'.
        Es idempotente y seguro.
        """
        # Importación local para evitar ciclos con PaymentService
        from .payments import PaymentService

        try:
            self._validate_signature()

            transaction_data = self.data.get("transaction", {})
            reference = transaction_data.get("reference")
            transaction_status = transaction_data.get("status")

            if not reference or not transaction_status:
                logger.error(
                    "[PAYMENT-ALERT] Webhook Error: Referencia o estado ausentes (event=%s)", self.event_type)
                raise ValueError(
                    "Referencia o estado de la transacción ausentes en el webhook.")

            try:
                payment = Payment.objects.select_for_update().get(
                    transaction_id=reference,
                    status=Payment.PaymentStatus.PENDING,
                )
            except Payment.DoesNotExist:
                try:
                    order = Order.objects.select_for_update().get(wompi_transaction_id=reference)
                except Order.DoesNotExist:
                    self._update_event_status(
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
                        self._update_event_status(
                            WebhookEvent.Status.FAILED, "Diferencia en montos detectada.")
                        logger.error(
                            "[PAYMENT-ALERT] Webhook Error: Diferencia en montos detectada (reference=%s expected=%s got=%s)",
                            reference,
                            expected_cents,
                            amount_in_cents,
                        )
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
                            self._update_event_status(
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
                        self._update_event_status(
                            WebhookEvent.Status.FAILED, str(exc))
                        logger.error("[PAYMENT-ALERT] Webhook Error: %s", exc)
                        return {"status": "fraud_alert"}
                else:
                    from marketplace.services import OrderService
                    OrderService.transition_to(
                        order, Order.OrderStatus.CANCELLED)
                self._update_event_status(WebhookEvent.Status.PROCESSED)
                return {"status": "order_processed", "order_id": str(order.id)}

            amount_in_cents = transaction_data.get("amount_in_cents")
            if amount_in_cents is not None and payment.amount is not None:
                expected_cents = int(payment.amount * 100)
                if int(amount_in_cents) != expected_cents:
                    payment.status = Payment.PaymentStatus.ERROR
                    payment.raw_response = transaction_data
                    payment.save(update_fields=["status", "raw_response", "updated_at"])
                    self._update_event_status(
                        WebhookEvent.Status.FAILED, "Diferencia en montos detectada en webhook."
                    )
                    logger.error(
                        "[PAYMENT-ALERT] Webhook Error: Diferencia en montos detectada (payment=%s expected=%s got=%s)",
                        payment.id,
                        expected_cents,
                        amount_in_cents,
                    )
                    return {"status": "amount_mismatch"}

            PaymentService.apply_gateway_status(
                payment, transaction_status, transaction_data)
            self._update_event_status(WebhookEvent.Status.PROCESSED)
            return {"status": "processed_successfully", "payment_id": payment.id}
        except Exception as exc:
            self._update_event_status(WebhookEvent.Status.FAILED, str(exc))
            logger.error("[PAYMENT-ALERT] Webhook Error: %s",
                         exc, exc_info=True)
            raise
