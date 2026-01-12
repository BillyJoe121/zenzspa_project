"""
DEPRECATED: Este módulo es una capa de compatibilidad.

Los imports de métricas han sido movidos a core.infra.metrics
Por favor actualiza tus imports a:
    from core.infra.metrics import get_histogram, get_counter

Este archivo será removido en futuras versiones.
"""
import warnings

# Re-exportar todo desde la nueva ubicación
from core.infra.metrics import *  # noqa: F401, F403

warnings.warn(
    "Importing from 'core.metrics' is deprecated. "
    "Use 'core.infra.metrics' instead.",
    DeprecationWarning,
    stacklevel=2
)
