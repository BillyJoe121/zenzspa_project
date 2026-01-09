"""
Cobros Recurrentes con Token de Pago.

Contiene:
- charge_recurrence_token: Ejecuta cobro recurrente usando payment_source_id
"""
import logging
import uuid
from decimal import Decimal

from django.conf import settings

from finances.gateway import WompiPaymentClient, build_integrity_signature
from finances.models import Payment


logger = logging.getLogger(__name__)


def charge_recurrence_token(user, amount, token):
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
