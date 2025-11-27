import hashlib
import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from core.exceptions import BusinessLogicError
from core.models import AuditLog, GlobalSettings
from finances.gateway import WompiGateway, WompiPaymentClient, build_integrity_signature
from finances.services import DeveloperCommissionService
from marketplace.models import Order
from users.models import CustomUser
from ..models import (
    Appointment,
    ClientCredit,
    FinancialAdjustment,
    Payment,
    PaymentCreditUsage,
    SubscriptionLog,
    Voucher,
    WebhookEvent,
)
from .vip import VipSubscriptionService
from .vouchers import PackagePurchaseService

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


class PaymentService:
    """
    Servicio para manejar la lógica de negocio de los pagos,
    incluyendo la aplicación de saldo a favor (ClientCredit).
    """
    WOMPI_DEFAULT_BASE_URL = "https://production.wompi.co/v1"

    def __init__(self, user):
        self.user = user

    @staticmethod
    def apply_gateway_status(payment, gateway_status, transaction_payload=None):
        normalized = (gateway_status or "").upper()
        previous_status = payment.status
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
                PackagePurchaseService.fulfill_purchase(payment)
            elif payment.payment_type == Payment.PaymentType.ADVANCE and payment.appointment:
                payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                payment.appointment.save(
                    update_fields=['status', 'updated_at'])
            elif payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION:
                VipSubscriptionService.fulfill_subscription(payment)
            elif (
                payment.payment_type == Payment.PaymentType.FINAL
                and payment.appointment
            ):
                payment.appointment.status = Appointment.AppointmentStatus.PAID
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
        PaymentService._send_payment_status_notification(
            payment=payment,
            new_status=payment.status,
            previous_status=previous_status,
            transaction_payload=transaction_payload,
        )
        return payment.status

    @staticmethod
    def poll_pending_payment(payment, timeout_minutes=30):
        if payment.status != Payment.PaymentStatus.PENDING:
            return False
        if not payment.transaction_id:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        client = WompiGateway()
        try:
            transaction = client.fetch_transaction(payment.transaction_id)
        except Exception:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        if not transaction:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        transaction_data = transaction.get('data') or transaction
        transaction_status = transaction_data.get('status')
        if not transaction_status:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        PaymentService.apply_gateway_status(
            payment, transaction_status, transaction_data)
        return True

    @classmethod
    def charge_recurrence_token(cls, user, amount, token):
        """
        Ejecuta un cobro recurrente usando una fuente de pago (payment_source_id)
        previamente creada en Wompi (Cards, Nequi, Daviplata, Bancolombia, etc.).

        Retorna:
            (Payment.PaymentStatus, transaction_payload (dict), reference (str))
        """
        if user is None:
            raise ValueError(
                "El usuario es requerido para el cobro recurrente.")

        if token is None:
            raise ValueError(
                "El token de pago es obligatorio para el cobro recurrente.")

        # El token debe ser el ID numérico de la fuente de pago (payment_source_id)
        try:
            if isinstance(token, str):
                token_str = token.strip()
                if not token_str:
                    raise ValueError(
                        "El token de pago es obligatorio para el cobro recurrente.")
                payment_source_id = int(token_str)
            else:
                payment_source_id = int(token)
        except (TypeError, ValueError):
            raise ValueError(
                "El token de cobro recurrente debe ser el ID numérico de la fuente de pago (payment_source_id)."
            )

        if amount is None:
            raise ValueError(
                "El monto es obligatorio para el cobro recurrente.")

        amount_decimal = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amount_decimal <= Decimal('0'):
            raise ValueError(
                "El monto debe ser mayor a cero para el cobro recurrente.")

        base_url = getattr(settings, 'WOMPI_BASE_URL',
                           cls.WOMPI_DEFAULT_BASE_URL) or cls.WOMPI_DEFAULT_BASE_URL
        base_url = base_url.rstrip('/') or cls.WOMPI_DEFAULT_BASE_URL

        private_key = getattr(settings, 'WOMPI_PRIVATE_KEY', '')
        if not private_key:
            logger.error(
                "WOMPI_PRIVATE_KEY no configurada; no se pudo cobrar la renovación VIP para el usuario %s.",
                user.id,
            )
            return Payment.PaymentStatus.DECLINED, {"error": "missing_private_key"}, None

        customer_email = getattr(user, "email", None)
        if not customer_email:
            logger.error(
                "El usuario %s no tiene correo electrónico registrado; no es posible crear el cobro recurrente.",
                user.id,
            )
            return Payment.PaymentStatus.DECLINED, {"error": "missing_email"}, None

        currency = getattr(settings, "WOMPI_CURRENCY", "COP") or "COP"
        amount_in_cents = int(amount_decimal * Decimal('100'))
        reference = f"VIP-AUTO-{user.id}-{uuid.uuid4().hex[:8]}"

        payload = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "customer_email": customer_email,
            "reference": reference,
            "payment_source_id": payment_source_id,
            "recurrent": True,
        }

        # Firma de integridad, si está configurada
        signature = cls._build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
        )
        if signature:
            payload["signature"] = signature

        headers = {
            "Authorization": f"Bearer {private_key}",
            "Content-Type": "application/json",
        }

        client = WompiPaymentClient(base_url=base_url, private_key=private_key)
        try:
            response_data, status_code = client.create_transaction(payload)
        except requests.RequestException as exc:
            logger.exception(
                "Error comunicándose con Wompi al intentar renovar VIP para el usuario %s",
                user.id,
            )
            return Payment.PaymentStatus.DECLINED, {"error": str(exc), "reference": reference}, reference

        if status_code >= 400:
            logger.warning(
                "Wompi rechazó el cobro recurrente para el usuario %s con payload %s",
                user.id,
                response_data,
            )

        transaction_data = response_data.get("data") or response_data
        wompi_status = (transaction_data.get("status") or "").upper()

        # Aseguramos que siempre haya referencia en el payload devuelto
        if "reference" not in transaction_data:
            transaction_data["reference"] = reference

        pending_statuses = {"PENDING", "WAITING", "PROCESSING"}
        if wompi_status == "APPROVED":
            normalized = Payment.PaymentStatus.APPROVED
        elif wompi_status in pending_statuses:
            normalized = Payment.PaymentStatus.PENDING
        else:
            normalized = Payment.PaymentStatus.DECLINED

        if normalized == Payment.PaymentStatus.APPROVED:
            logger.info(
                "Cobro VIP recurrente aprobado para el usuario %s (ref=%s, source_id=%s).",
                user.id,
                reference,
                payment_source_id,
            )
        elif normalized == Payment.PaymentStatus.PENDING:
            logger.info(
                "Cobro VIP recurrente en estado pendiente para el usuario %s (ref=%s, source_id=%s).",
                user.id,
                reference,
                payment_source_id,
            )
        else:
            logger.warning(
                "Cobro VIP recurrente no aprobado para el usuario %s (estado=%s, source_id=%s).",
                user.id,
                wompi_status or "DESCONOCIDO",
                payment_source_id,
            )

        return normalized, transaction_data, reference

    @classmethod
    def _build_integrity_signature(cls, *, reference, amount_in_cents, currency):
        return build_integrity_signature(reference, amount_in_cents, currency)

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

    @staticmethod
    @transaction.atomic
    def create_tip_payment(appointment: Appointment, user, amount):
        if appointment.status not in [
            Appointment.AppointmentStatus.COMPLETED,
            Appointment.AppointmentStatus.PAID,
        ]:
            raise ValidationError(
                "Solo se pueden registrar propinas para citas completadas.")
        return Payment.objects.create(
            user=user,
            appointment=appointment,
            amount=amount,
            payment_type=Payment.PaymentType.TIP,
            status=Payment.PaymentStatus.APPROVED,
        )

    @staticmethod
    def calculate_outstanding_amount(appointment: Appointment):
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

    @staticmethod
    @transaction.atomic
    def create_final_payment(appointment: Appointment, user):
        outstanding = PaymentService.calculate_outstanding_amount(appointment)
        payment = None
        if outstanding > Decimal('0'):
            payment = Payment.objects.create(
                user=user,
                appointment=appointment,
                amount=outstanding,
                payment_type=Payment.PaymentType.FINAL,
                status=Payment.PaymentStatus.APPROVED,
            )
        appointment.status = Appointment.AppointmentStatus.PAID
        appointment.save(update_fields=['status', 'updated_at'])
        return payment, outstanding

    @classmethod
    def _resolve_acceptance_token(cls, base_url):
        return WompiPaymentClient.resolve_acceptance_token(base_url=base_url)

    @classmethod
    def create_pse_payment(
        cls,
        *,
        payment: Payment,
        user_type: int,
        user_legal_id: str,
        user_legal_id_type: str,
        financial_institution_code: str,
        payment_description: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """
        Crea una transacción PSE en Wompi para un pago existente.

        Args:
            payment: Objeto Payment previamente creado con status PENDING
            user_type: 0=Persona Natural, 1=Persona Jurídica
            user_legal_id: Número de documento (CC, NIT, etc.)
            user_legal_id_type: Tipo de documento (CC, NIT, CE, etc.)
            financial_institution_code: Código del banco PSE
            payment_description: Descripción del pago (max 30 caracteres)
            redirect_url: URL de redirección después del pago
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code de Wompi

        Example:
            data, status = PaymentService.create_pse_payment(
                payment=payment,
                user_type=0,
                user_legal_id="1234567890",
                user_legal_id_type="CC",
                financial_institution_code="1022",
                payment_description="Pago cita spa",
            )
        """
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción PSE")

        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)

        # Actualizar campos del modelo Payment
        payment.customer_legal_id = user_legal_id
        payment.customer_legal_id_type = user_legal_id_type
        payment.payment_method_type = "PSE"
        payment.payment_method_data = {
            "financial_institution_code": financial_institution_code,
            "payment_description": payment_description,
            "user_type": user_type,
        }

        response_data, status_code = client.create_pse_transaction(
            amount_in_cents=amount_in_cents,
            reference=payment.transaction_id,
            customer_email=payment.user.email,
            user_type=user_type,
            user_legal_id=user_legal_id,
            user_legal_id_type=user_legal_id_type,
            financial_institution_code=financial_institution_code,
            payment_description=payment_description,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )

        if status_code == 201:
            transaction_data = response_data.get("data", {})
            payment.raw_response = transaction_data
            # Extraer async_payment_url de PSE para redirección
            if "payment_method" in transaction_data:
                extra = transaction_data["payment_method"].get("extra", {})
                if "async_payment_url" in extra:
                    payment.payment_method_data["async_payment_url"] = extra["async_payment_url"]

        payment.save(update_fields=[
            'customer_legal_id',
            'customer_legal_id_type',
            'payment_method_type',
            'payment_method_data',
            'raw_response',
            'updated_at'
        ])

        return response_data, status_code

    @classmethod
    def create_nequi_payment(
        cls,
        *,
        payment: Payment,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """
        Crea una transacción Nequi en Wompi para un pago existente.

        Args:
            payment: Objeto Payment previamente creado con status PENDING
            phone_number: Número de celular Nequi (10 dígitos, sin +57)
            redirect_url: URL de redirección después del pago
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code de Wompi

        Example:
            data, status = PaymentService.create_nequi_payment(
                payment=payment,
                phone_number="3001234567",
            )
        """
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción Nequi")

        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)

        # Actualizar campos del modelo Payment
        payment.payment_method_type = "NEQUI"
        payment.payment_method_data = {"phone_number": phone_number}

        response_data, status_code = client.create_nequi_transaction(
            amount_in_cents=amount_in_cents,
            reference=payment.transaction_id,
            customer_email=payment.user.email,
            phone_number=phone_number,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )

        if status_code == 201:
            transaction_data = response_data.get("data", {})
            payment.raw_response = transaction_data
            # Extraer async_payment_url de Nequi para redirección
            if "payment_method" in transaction_data:
                extra = transaction_data["payment_method"].get("extra", {})
                if "async_payment_url" in extra:
                    payment.payment_method_data["async_payment_url"] = extra["async_payment_url"]

        payment.save(update_fields=[
            'payment_method_type',
            'payment_method_data',
            'raw_response',
            'updated_at'
        ])

        return response_data, status_code

    @staticmethod
    def _send_payment_status_notification(*, payment, new_status, previous_status, transaction_payload):
        if new_status not in (
            Payment.PaymentStatus.APPROVED,
            Payment.PaymentStatus.DECLINED,
            Payment.PaymentStatus.ERROR,
        ):
            return
        if previous_status == new_status:
            return
        user = getattr(payment, "user", None)
        email = getattr(user, "email", None)
        if not user or not email:
            return
        reference = None
        if isinstance(transaction_payload, dict):
            reference = transaction_payload.get(
                "id") or transaction_payload.get("reference")
        reference = reference or payment.transaction_id
        amount = payment.amount or Decimal('0')
        amount_str = f"{amount:,.2f}"
        payment_type = payment.get_payment_type_display()
        timestamp = timezone.localtime().strftime("%d/%m/%Y %H:%M")
        display_name = user.get_full_name() if hasattr(
            user, "get_full_name") else (user.first_name or "")
        display_name = display_name or user.email
        # Refactor: Use NotificationService instead of direct send_mail
        from notifications.services import NotificationService

        event_code = None
        if new_status == Payment.PaymentStatus.APPROVED:
            event_code = "PAYMENT_STATUS_APPROVED"
        elif new_status == Payment.PaymentStatus.DECLINED:
            event_code = "PAYMENT_STATUS_DECLINED"
        elif new_status == Payment.PaymentStatus.ERROR:
            event_code = "PAYMENT_STATUS_ERROR"
        
        if not event_code:
            return

        context = {
            "amount": amount_str,
            "payment_type": payment_type,
            "reference": reference or "N/A",
            "date": timestamp,
            "display_name": display_name,
            "payment_id": payment.id,
        }

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

    @staticmethod
    def reset_user_cancellation_history(appointment: Appointment):
        user = getattr(appointment, "user", None)
        if not user:
            return
        streak = getattr(user, "cancellation_streak", None)
        if streak:
            user.cancellation_streak = []
            user.save(update_fields=['cancellation_streak', 'updated_at'])


class FinancialAdjustmentService:
    CREDIT_TTL_DAYS = 365
    MAX_MANUAL_ADJUSTMENT = Decimal("5000000")

    @classmethod
    @transaction.atomic
    def create_adjustment(cls, *, user, amount, adjustment_type, reason, created_by, related_payment=None):
        if amount <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")
        if Decimal(amount) > cls.MAX_MANUAL_ADJUSTMENT:
            raise BusinessLogicError(
                detail="El monto excede el límite permitido para ajustes manuales.",
                internal_code="PAY-ADJ-LIMIT",
            )
        adjustment = FinancialAdjustment.objects.create(
            user=user,
            amount=amount,
            adjustment_type=adjustment_type,
            reason=reason,
            related_payment=related_payment,
            created_by=created_by,
        )
        details_parts = [
            f"Tipo: {adjustment.get_adjustment_type_display()}",
            f"Monto: COP {Decimal(amount):,.2f}",
        ]
        if reason:
            details_parts.append(f"Razón: {reason}")
        if related_payment:
            details_parts.append(f"Pago relacionado: {related_payment.id}")
        AuditLog.objects.create(
            admin_user=created_by,
            target_user=user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=" | ".join(details_parts),
        )
        if adjustment_type == FinancialAdjustment.AdjustmentType.CREDIT:
            expires = timezone.now().date() + timedelta(days=cls.CREDIT_TTL_DAYS)
            ClientCredit.objects.create(
                user=user,
                originating_payment=related_payment,
                initial_amount=amount,
                remaining_amount=amount,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires,
            )
        return adjustment
