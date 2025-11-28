import logging
from typing import Optional, Dict, Any

from django.db import transaction

from .models import GlobalSettings, AuditLog

logger = logging.getLogger(__name__)

def get_setting(key: str, default=None):
    """
    Obtiene un atributo puntual del singleton de settings.

    Args:
        key: nombre del campo en GlobalSettings.
        default: valor devuelto si no existe o falla la carga.
    """
    if not key:
        raise ValueError("key es obligatorio para obtener un setting.")

    try:
        settings = GlobalSettings.load()
    except Exception as exc:
        logger.exception("No se pudo cargar GlobalSettings al obtener '%s'", key)
        return default

    if not hasattr(settings, key):
        logger.warning("GlobalSettings no tiene el atributo '%s'. Se usa default.", key)
        return default

    try:
        value = getattr(settings, key)
    except Exception as exc:
        logger.exception("Error al acceder al atributo '%s' de GlobalSettings", key)
        return default

    return value if value is not None else default

@transaction.atomic
def admin_flag_non_grata(admin_user, target_user, details: Optional[Dict[str, Any]] = None):
    """
    Registra en auditoría un flag manual sobre un usuario.

    Nota: el bloqueo efectivo y acciones posteriores las gestiona el módulo users.

    Returns:
        bool: True si el registro se creó correctamente.
    """
    AuditLog.objects.create(
        action=AuditLog.Action.FLAG_NON_GRATA,
        admin_user=admin_user,
        target_user=target_user,
        details=details or {},
    )
    return True
