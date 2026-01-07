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
    PaymentToken,
    CommissionLedger,
)
from marketplace.models import Order
from users.models import CustomUser
from core.models import IdempotencyKey
from core.metrics import get_counter

logger = logging.getLogger(__name__)

webhook_signature_errors = get_counter(
    "webhook_signature_errors_total",
    "Errores de firma en webhooks de Wompi",
    ["event_type"],
)

payment_failures = get_counter(
    "payment_failures_total",
    "Pagos fallidos por razón",
    ["reason", "gateway"],
)


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
            webhook_signature_errors.labels(self.event_type or "unknown").inc()
            raise ValueError("Firma del webhook incompleta.")

        # Validar frescura del timestamp para prevenir replays
        try:
            event_ts = int(self.timestamp)
        except (TypeError, ValueError):
            logger.error("[PAYMENT-ALERT] Webhook Error: Timestamp inválido (event=%s)", self.event_type)
            raise ValueError("Timestamp inválido en webhook.")

        now_ts = int(timezone.now().timestamp())
        if abs(now_ts - event_ts) > 300:
            logger.error(
                "[PAYMENT-ALERT] Webhook Error: Timestamp fuera de ventana (event=%s, ts=%s, now=%s)",
                self.event_type,
                self.timestamp,
                now_ts,
            )
            raise ValueError("Webhook demasiado antiguo o en el futuro.")

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
            webhook_signature_errors.labels(self.event_type or "unknown").inc()
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
                                from finances.cashback_service import CashbackService
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
                        payment_failures.labels(reason="fraud_check_failed", gateway="wompi").inc()
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
                    payment_failures.labels(reason="amount_mismatch", gateway="wompi").inc()
                    return {"status": "amount_mismatch"}

            PaymentService.apply_gateway_status(
                payment, transaction_status, transaction_data)
            self._update_event_status(WebhookEvent.Status.PROCESSED)
            idem_key.mark_completed(
                response_body={"payment_id": str(payment.id)},
                status_code=200,
            )
            return {"status": "processed_successfully", "payment_id": payment.id}
        except Exception as exc:
            self._update_event_status(WebhookEvent.Status.FAILED, str(exc))
            logger.error("[PAYMENT-ALERT] Webhook Error: %s",
                         exc, exc_info=True)
            payment_failures.labels(reason="unhandled_exception", gateway="wompi").inc()
            raise

    def process_token_update(self):
        """
        Procesa eventos de tokenización (nequi_token.updated, bancolombia_transfer_token.updated).
        Valida la firma y marca el evento como procesado para evitar reintentos.
        """
        try:
            self._validate_signature()
            token_data = self.data.get("token") or self.data.get("data") or {}
            token_id = token_data.get("id") or token_data.get("token")
            token_status = (token_data.get("status") or "").upper() or PaymentToken.TokenStatus.PENDING
            token_type = token_data.get("type") or token_data.get("payment_method_type") or ""
            phone_number = token_data.get("phone_number") or token_data.get("phone") or ""
            customer_email = token_data.get("customer_email") or self.data.get("customer_email") or ""

            linked_user = None
            if customer_email:
                linked_user = CustomUser.objects.filter(email__iexact=customer_email).first()
            if not linked_user and phone_number:
                linked_user = CustomUser.objects.filter(phone_number=phone_number).first()

            if not token_id:
                raise ValueError("No se encontró token_id en el evento de token.")

            fingerprint = PaymentToken.fingerprint(token_id)
            masked = PaymentToken.mask_token(token_id)

            PaymentToken.objects.update_or_create(
                token_fingerprint=fingerprint,
                defaults={
                    "token_id": masked,
                    "token_secret": token_id,
                    "status": token_status,
                    "token_type": token_type,
                    "phone_number": phone_number or "",
                    "customer_email": customer_email or "",
                    "raw_payload": self.data,
                    "user": linked_user,
                },
            )

            self._update_event_status(WebhookEvent.Status.PROCESSED)
            logger.info(
                "[PAYMENT-SUCCESS] Evento de token procesado (event=%s, token=%s, status=%s)",
                self.event_type,
                masked,
                token_status,
            )
            return {"status": "token_event_processed", "token_id": masked, "token_status": token_status}
        except Exception as exc:
            self._update_event_status(WebhookEvent.Status.FAILED, str(exc))
            logger.error("[PAYMENT-ALERT] Webhook Token Error: %s", exc, exc_info=True)
            raise

    @transaction.atomic
    def process_payout_update(self):
        """
        Procesa eventos de payout/transfer (dispersión) para reflejar estado final.
        """
        try:
            self._validate_signature()

            transfer_data = self.data.get("transfer") or self.data.get("data") or {}
            transfer_id = transfer_data.get("id") or transfer_data.get("transfer_id")
            status = (transfer_data.get("status") or "").upper()

            if not transfer_id or not status:
                raise ValueError("transfer_id o status no presentes en el webhook de payout.")

            # Actualizar las comisiones asociadas al transfer_id
            entries = CommissionLedger.objects.select_for_update().filter(wompi_transfer_id=transfer_id)
            updated = 0
            now = timezone.now()
            for entry in entries:
                previous_status = entry.status
                if status == "APPROVED":
                    entry.status = CommissionLedger.Status.PAID
                    entry.paid_at = entry.paid_at or now
                elif status in {"DECLINED", "ERROR"}:
                    entry.status = CommissionLedger.Status.FAILED_NSF
                entry.save(update_fields=["status", "paid_at", "updated_at"])
                updated += 1

            self._update_event_status(WebhookEvent.Status.PROCESSED)
            logger.info(
                "[PAYMENT-SUCCESS] Evento de payout procesado (transfer_id=%s, status=%s, entries_updated=%s)",
                transfer_id,
                status,
                updated,
            )
            return {"status": "payout_event_processed", "transfer_id": transfer_id, "transfer_status": status, "entries_updated": updated}
        except Exception as exc:
            self._update_event_status(WebhookEvent.Status.FAILED, str(exc))
            logger.error("[PAYMENT-ALERT] Webhook Payout Error: %s", exc, exc_info=True)
            raise
