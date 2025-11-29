"""
Módulo de modelos core.

Exporta todos los modelos y constantes para mantener compatibilidad con imports existentes.
"""
from .audit import AuditLog
from .base import BaseModel, SoftDeleteManager, SoftDeleteModel, SoftDeleteQuerySet
from .idempotency import IdempotencyKey
from .notifications import AdminNotification
from .settings import GLOBAL_SETTINGS_SINGLETON_UUID, GlobalSettings

# Importar GLOBAL_SETTINGS_CACHE_KEY desde el módulo centralizado de caché
from ..caching import GLOBAL_SETTINGS_CACHE_KEY

__all__ = [
    # Base models
    'BaseModel',
    'SoftDeleteQuerySet',
    'SoftDeleteManager',
    'SoftDeleteModel',
    # Audit
    'AuditLog',
    # Settings
    'GlobalSettings',
    'GLOBAL_SETTINGS_CACHE_KEY',
    'GLOBAL_SETTINGS_SINGLETON_UUID',
    # Idempotency
    'IdempotencyKey',
    # Notifications
    'AdminNotification',
]
