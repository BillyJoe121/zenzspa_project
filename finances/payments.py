import logging
import uuid
import requests
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessLogicError
from core.models import GlobalSettings
from finances.gateway import WompiGateway, WompiPaymentClient, build_integrity_signature
from finances.services import DeveloperCommissionService
from finances.subscriptions import VipSubscriptionService
from finances.models import (
    ClientCredit,
    Payment,
    PaymentCreditUsage,
)
from spa.models import Appointment
# PackagePurchaseService se importa de forma lazy para evitar ciclo circular

logger = logging.getLogger(__name__)


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
                    # Use PaymentService to calculate outstanding (includes APPROVED + PAID_WITH_CREDIT)
                    outstanding = PaymentService.calculate_outstanding_amount(payment.appointment)

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
                    # Use PaymentService to calculate outstanding (includes APPROVED + PAID_WITH_CREDIT)
                    outstanding = PaymentService.calculate_outstanding_amount(payment.appointment)

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
            transaction_payload=transaction_payload
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
        transaction = client.fetch_transaction(payment.transaction_id)
        
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

    @staticmethod
    def _build_tax_payload(payment: Payment) -> dict:
        """Construye tax_in_cents para Wompi si el pago tiene impuestos registrados."""
        tax_payload = {}
        if payment.tax_vat_in_cents is not None:
            tax_payload["vat"] = payment.tax_vat_in_cents
        if payment.tax_consumption_in_cents is not None:
            tax_payload["consumption"] = payment.tax_consumption_in_cents
        return tax_payload

    @staticmethod
    def _build_customer_data(payment: Payment) -> dict:
        """Construye customer_data para Wompi a partir del pago y el usuario."""
        customer_data: dict = {}
        if payment.customer_legal_id:
            customer_data["legal_id"] = payment.customer_legal_id
        if payment.customer_legal_id_type:
            customer_data["legal_id_type"] = payment.customer_legal_id_type

        user = getattr(payment, "user", None)
        if user:
            full_name = ""
            try:
                full_name = user.get_full_name()
            except Exception:
                full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            if full_name:
                customer_data["full_name"] = full_name
            phone = getattr(user, "phone_number", None)
            if phone:
                customer_data["phone_number"] = phone
        return customer_data

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

        # Firma de integridad
        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
        )
        if signature:
            payload["signature"] = {"integrity": signature}

        client = WompiPaymentClient()
        try:
            response_data, status_code = client.create_transaction(payload)
        except Exception as exc:
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

    @staticmethod
    @transaction.atomic
    def create_package_payment(user, package):
        """
        Crea un registro de pago para la compra de un paquete.
        """
        reference = f"PACKAGE-{package.id}-{uuid.uuid4().hex[:8]}"
        
        payment = Payment.objects.create(
            user=user,
            amount=package.price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.PACKAGE,
            transaction_id=reference
        )
        return payment

    @staticmethod
    @transaction.atomic
    def create_order_payment(user, order):
        """
        Crea o actualiza un registro de pago para una orden de marketplace 
        y prepara los datos para Wompi con una referencia única.
        """
        # Generar SIEMPRE una nueva referencia para permitir reintentos
        reference = f"ORDER-{order.id}-{uuid.uuid4().hex[:8]}"
        
        # Buscar si ya existe un pago pendiente para esta orden para reutilizarlo
        payment = Payment.objects.filter(
            order=order, 
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ORDER
        ).first()

        if payment:
            # Actualizar pago existente con nueva referencia
            payment.transaction_id = reference
            payment.amount = order.total_amount
            payment.user = user # Asegurar que el usuario sea el correcto
            payment.save(update_fields=['transaction_id', 'amount', 'user', 'updated_at'])
        else:
            # Crear nuevo pago
            payment = Payment.objects.create(
                user=user,
                amount=order.total_amount,
                status=Payment.PaymentStatus.PENDING,
                payment_type=Payment.PaymentType.ORDER,
                transaction_id=reference,
                order=order,
            )
        
        order.wompi_transaction_id = reference
        order.save(update_fields=['wompi_transaction_id', 'updated_at'])
        
        amount_in_cents = int(order.total_amount * 100)
        
        # Obtener acceptance token
        try:
            acceptance_token = WompiPaymentClient.resolve_acceptance_token()
            if not acceptance_token:
                 raise ValueError("No se pudo obtener el token de aceptación de Wompi.")
        except requests.RequestException as e:
            raise ValueError(f"Error al comunicarse con Wompi: {str(e)}")

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=getattr(settings, "WOMPI_CURRENCY", "COP"),
        )

        payment_payload = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': getattr(settings, "WOMPI_CURRENCY", "COP"),
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,
            'redirectUrl': settings.WOMPI_REDIRECT_URL,
            'acceptanceToken': acceptance_token,
            'paymentId': str(payment.id),
        }
        
        return payment, payment_payload

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
            DeveloperCommissionService.handle_successful_payment(payment)

            # Recalculate outstanding to determine new status
            # Use PaymentService to ensure consistency (includes APPROVED + PAID_WITH_CREDIT)
            outstanding_after = PaymentService.calculate_outstanding_amount(appointment)

            if outstanding_after <= Decimal('0'):
                appointment.status = Appointment.AppointmentStatus.FULLY_PAID
            else:
                appointment.status = Appointment.AppointmentStatus.CONFIRMED
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
        """
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción PSE")

        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)

        # Preparar datos opcionales (impuestos y customer_data)
        taxes = cls._build_tax_payload(payment)
        customer_data = cls._build_customer_data(payment)

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
            taxes=taxes,
            customer_data=customer_data,
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
        """
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción Nequi")

        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)

        taxes = cls._build_tax_payload(payment)
        customer_data = cls._build_customer_data(payment)

        # Actualizar campos del modelo Payment
        payment.payment_method_type = "NEQUI"
        payment.payment_method_data = {
            "phone_number": phone_number,
        }

        response_data, status_code = client.create_nequi_transaction(
            amount_in_cents=amount_in_cents,
            reference=payment.transaction_id,
            customer_email=payment.user.email,
            phone_number=phone_number,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
            taxes=taxes,
            customer_data=customer_data,
        )

        if status_code == 201:
            transaction_data = response_data.get("data", {})
            payment.raw_response = transaction_data

        payment.save(update_fields=[
            'payment_method_type',
            'payment_method_data',
            'raw_response',
            'updated_at'
        ])

        return response_data, status_code

    @classmethod
    def create_daviplata_payment(
        cls,
        *,
        payment: Payment,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción Daviplata en Wompi para un pago existente."""
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción Daviplata")
        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)
        taxes = cls._build_tax_payload(payment)
        customer_data = cls._build_customer_data(payment)

        payment.payment_method_type = "DAVIPLATA"
        payment.payment_method_data = {"phone_number": phone_number}

        response_data, status_code = client.create_daviplata_transaction(
            amount_in_cents=amount_in_cents,
            reference=payment.transaction_id,
            customer_email=payment.user.email,
            phone_number=phone_number,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
            taxes=taxes,
            customer_data=customer_data,
        )

        if status_code == 201:
            transaction_data = response_data.get("data", {})
            payment.raw_response = transaction_data

        payment.save(update_fields=[
            'payment_method_type',
            'payment_method_data',
            'raw_response',
            'updated_at'
        ])

        return response_data, status_code

    @classmethod
    def create_bancolombia_transfer_payment(
        cls,
        *,
        payment: Payment,
        payment_description: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción Bancolombia Transfer (Botón) en Wompi para un pago existente."""
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValueError("El pago debe estar en estado PENDING para crear la transacción Bancolombia Transfer")
        if not payment.user:
            raise ValueError("El pago debe tener un usuario asociado")

        client = WompiPaymentClient()
        amount_in_cents = int(payment.amount * 100)
        taxes = cls._build_tax_payload(payment)
        customer_data = cls._build_customer_data(payment)

        payment.payment_method_type = "BANCOLOMBIA_TRANSFER"
        payment.payment_method_data = {"payment_description": payment_description}

        response_data, status_code = client.create_bancolombia_transfer_transaction(
            amount_in_cents=amount_in_cents,
            reference=payment.transaction_id,
            customer_email=payment.user.email,
            payment_description=payment_description,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
            taxes=taxes,
            customer_data=customer_data,
        )

        if status_code == 201:
            transaction_data = response_data.get("data", {})
            payment.raw_response = transaction_data
            # async_payment_url puede venir en extra o en payment_method directamente
            async_url = None
            payment_method = transaction_data.get("payment_method", {})
            extra = payment_method.get("extra", {}) if isinstance(payment_method, dict) else {}
            async_url = (
                payment_method.get("async_payment_url")
                if isinstance(payment_method, dict)
                else None
            )
            if not async_url:
                async_url = extra.get("async_payment_url")
            if async_url:
                payment.payment_method_data["async_payment_url"] = async_url

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

        service_description = PaymentService._describe_payment_service(payment)
        if event_code == "PAYMENT_STATUS_APPROVED":
            context = {
                **base_context,
                "service": service_description,
            }
        elif event_code == "PAYMENT_STATUS_DECLINED":
            context = {
                **base_context,
                "decline_reason": PaymentService._extract_decline_reason(transaction_payload),
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

    @staticmethod
    def _describe_payment_service(payment):
        appointment = getattr(payment, "appointment", None)
        if appointment:
            try:
                services = appointment.get_service_names()
            except Exception:
                services = ""
            if services:
                return services
            return "Servicios de tu cita"

        order = getattr(payment, "order", None)
        if order:
            return f"Orden #{order.id}"

        payment_type_display = payment.get_payment_type_display()
        if payment_type_display:
            return payment_type_display
        return "Pago en StudioZens"

    @staticmethod
    def _extract_decline_reason(transaction_payload):
        default_reason = "El banco rechazó la transacción. Intenta nuevamente."
        if not isinstance(transaction_payload, dict):
            return default_reason

        candidates = [
            "status_message",
            "status_detail",
            "status_reason",
            "reason",
            "error",
            "message",
            "response_message",
        ]
        for key in candidates:
            value = transaction_payload.get(key)
            if value:
                return str(value)

        payment_method = transaction_payload.get("payment_method") or {}
        extra = payment_method.get("extra") or {}
        for key in ("status", "status_message", "message", "reason"):
            value = extra.get(key)
            if value:
                return str(value)

        processor = transaction_payload.get("processor_fields") or {}
        for key in ("explanation", "message", "status_message"):
            value = processor.get(key)
            if value:
                return str(value)

        return default_reason

    @staticmethod
    def reset_user_cancellation_history(appointment: Appointment):
        user = getattr(appointment, "user", None)
        if not user:
            return
        streak = getattr(user, "cancellation_streak", None)
        if streak:
            user.cancellation_streak = []
            user.save(update_fields=['cancellation_streak', 'updated_at'])

    @staticmethod
    def generate_checkout_url(payment: Payment) -> str:
        """
        Genera una URL de checkout hosted de Wompi para el pago.
        
        Esta URL puede ser enviada al cliente por WhatsApp para que complete
        el pago sin necesidad de estar en la app.
        
        Returns:
            str: URL completa de checkout de Wompi
        """
        import urllib.parse
        
        amount_in_cents = int(payment.amount * 100)
        reference = payment.transaction_id or f"PAY-{str(payment.id)[-12:]}"
        
        # Actualizar transaction_id si no existe
        if not payment.transaction_id:
            payment.transaction_id = reference
            payment.save(update_fields=['transaction_id', 'updated_at'])
        
        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )
        
        public_key = settings.WOMPI_PUBLIC_KEY
        redirect_url = urllib.parse.quote(settings.WOMPI_REDIRECT_URL, safe='')
        
        # Construir URL de checkout de Wompi
        checkout_url = (
            f"https://checkout.wompi.co/p/"
            f"?public-key={public_key}"
            f"&currency=COP"
            f"&amount-in-cents={amount_in_cents}"
            f"&reference={reference}"
            f"&signature:integrity={signature}"
            f"&redirect-url={redirect_url}"
        )
        
        return checkout_url

    @staticmethod
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

    @staticmethod
    def cancel_pending_payments_for_appointment(appointment):
        """
        Cancela todos los pagos pendientes asociados a una cita cuando esta es cancelada.

        Esto previene que los usuarios queden bloqueados por deuda de citas canceladas.
        Solo cancela pagos en estado PENDING (no afecta pagos ya aprobados o procesados).

        Args:
            appointment: La cita que fue cancelada

        Returns:
            int: Número de pagos cancelados
        """
        from finances.models import Payment

        # Solo cancelar pagos PENDING
        pending_payments = Payment.objects.filter(
            appointment=appointment,
            status=Payment.PaymentStatus.PENDING
        )

        count = pending_payments.count()
        if count > 0:
            pending_payments.update(
                status=Payment.PaymentStatus.CANCELLED,
                updated_at=timezone.now()
            )
            logger.info(
                "Cancelados %d pagos pendientes para cita %s",
                count,
                appointment.id
            )

        return count

