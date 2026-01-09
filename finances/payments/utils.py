"""
Utilidades de Pagos.

Contiene funciones auxiliares:
- generate_checkout_url: Genera URL de checkout Wompi
- reset_user_cancellation_history: Resetea historial de cancelaciones
- cancel_pending_payments_for_appointment: Cancela pagos pendientes
- _describe_payment_service: Descripción del servicio asociado al pago
- _extract_decline_reason: Extrae razón de rechazo del payload
- _build_tax_payload: Construye payload de impuestos
- _build_customer_data: Construye datos del cliente
"""
import logging
import urllib.parse
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from finances.gateway import build_integrity_signature
from finances.models import Payment


logger = logging.getLogger(__name__)


def build_tax_payload(payment: Payment) -> dict:
    """Construye tax_in_cents para Wompi si el pago tiene impuestos registrados."""
    tax_payload = {}
    if payment.tax_vat_in_cents is not None:
        tax_payload["vat"] = payment.tax_vat_in_cents
    if payment.tax_consumption_in_cents is not None:
        tax_payload["consumption"] = payment.tax_consumption_in_cents
    return tax_payload


def build_customer_data(payment: Payment) -> dict:
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


def describe_payment_service(payment):
    """Genera descripción legible del servicio asociado al pago."""
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


def extract_decline_reason(transaction_payload):
    """Extrae razón de rechazo del payload de Wompi."""
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


def reset_user_cancellation_history(appointment):
    """Resetea el historial de cancelaciones del usuario de una cita."""
    user = getattr(appointment, "user", None)
    if not user:
        return
    streak = getattr(user, "cancellation_streak", None)
    if streak:
        user.cancellation_streak = []
        user.save(update_fields=['cancellation_streak', 'updated_at'])


def generate_checkout_url(payment: Payment) -> str:
    """
    Genera una URL de checkout hosted de Wompi para el pago.
    
    Esta URL puede ser enviada al cliente por WhatsApp para que complete
    el pago sin necesidad de estar en la app.
    
    Returns:
        str: URL completa de checkout de Wompi
    """
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
