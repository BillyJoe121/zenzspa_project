import logging

from core.infra.metrics import get_counter

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
