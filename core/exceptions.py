"""
DEPRECATED: Este módulo es una capa de compatibilidad.

Los imports de excepciones han sido movidos a core.utils.exceptions
Por favor actualiza tus imports a:
    from core.utils.exceptions import BusinessLogicError

Este archivo será removido en futuras versiones.
"""
import warnings

# Re-exportar todo desde la nueva ubicación
from core.utils.exceptions import *  # noqa: F401, F403

warnings.warn(
    "Importing from 'core.exceptions' is deprecated. "
    "Use 'core.utils.exceptions' instead.",
    DeprecationWarning,
    stacklevel=2
)
