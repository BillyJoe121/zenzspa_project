"""
DEPRECADO: Este archivo ha sido migrado a finances.subscriptions

Los servicios VIP han sido movidos al módulo finances para centralizar
toda la lógica de pagos y suscripciones.

Para compatibilidad temporal, se re-exportan desde finances.subscriptions
en spa/services/__init__.py, pero deberías actualizar tus imports a:

    from finances.subscriptions import VipMembershipService, VipSubscriptionService

Este archivo será eliminado en una futura versión.
"""
import warnings

warnings.warn(
    "spa.services.vip está deprecado. "
    "Los servicios VIP han sido migrados a finances.subscriptions. "
    "Actualiza tus imports a 'from finances.subscriptions import VipSubscriptionService'",
    DeprecationWarning,
    stacklevel=2
)

# Re-exports para compatibilidad temporal
from finances.subscriptions import VipMembershipService, VipSubscriptionService

__all__ = ["VipMembershipService", "VipSubscriptionService"]
