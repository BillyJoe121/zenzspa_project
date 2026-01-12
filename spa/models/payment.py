"""
DEPRECADO: Este archivo ha sido migrado a finances.models

Todos los modelos de pagos, créditos y suscripciones han sido movidos
al módulo finances para centralizar la lógica financiera.

Para compatibilidad temporal, los modelos se re-exportan desde finances.models
en spa/models/__init__.py, pero deberías actualizar tus imports a:

    from finances.models import Payment, ClientCredit, etc.

Este archivo será eliminado en una futura versión.
"""
import warnings

warnings.warn(
    "spa.models.payment está deprecado. "
    "Los modelos de pago han sido migrados a finances.models. "
    "Actualiza tus imports a 'from finances.models import Payment'",
    DeprecationWarning,
    stacklevel=2
)

# Re-exports para compatibilidad temporal
from finances.models import (
    Payment,
    PaymentCreditUsage,
    ClientCredit,
    FinancialAdjustment,
    SubscriptionLog,
    WebhookEvent,
)

__all__ = [
    "Payment",
    "PaymentCreditUsage",
    "ClientCredit",
    "FinancialAdjustment",
    "SubscriptionLog",
    "WebhookEvent",
]
