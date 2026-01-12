"""
DEPRECADO: Este archivo ha sido migrado a finances.serializers

Los serializers de Payment y FinancialAdjustment han sido movidos
al módulo finances para centralizar la serialización de modelos financieros.

Para compatibilidad temporal, se re-exportan desde finances.serializers,
pero deberías actualizar tus imports a:

    from finances.serializers import PaymentSerializer, FinancialAdjustmentSerializer

Este archivo será eliminado en una futura versión.
"""
import warnings

warnings.warn(
    "spa.serializers.payment está deprecado. "
    "Los serializers de pago han sido migrados a finances.serializers. "
    "Actualiza tus imports a 'from finances.serializers import PaymentSerializer'",
    DeprecationWarning,
    stacklevel=2
)

# Re-exports para compatibilidad temporal
from finances.serializers import (
    PaymentSerializer,
    FinancialAdjustmentSerializer,
    FinancialAdjustmentCreateSerializer,
)

__all__ = [
    "PaymentSerializer",
    "FinancialAdjustmentSerializer",
    "FinancialAdjustmentCreateSerializer",
]
