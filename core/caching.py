"""
DEPRECATED: Este módulo es una capa de compatibilidad.

Los imports de caching han sido movidos a core.utils.caching
Por favor actualiza tus imports a:
    from core.utils.caching import acquire_lock

Este archivo será removido en futuras versiones.
"""
import warnings

# Re-exportar todo desde la nueva ubicación
from core.utils.caching import *  # noqa: F401, F403

warnings.warn(
    "Importing from 'core.caching' is deprecated. "
    "Use 'core.utils.caching' instead.",
    DeprecationWarning,
    stacklevel=2
)
