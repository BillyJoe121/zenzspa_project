from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction

from .models import GlobalSettings, AuditLog

GLOBAL_SETTINGS_CACHE_KEY = "global_settings"

@dataclass(frozen=True)
class SettingsDTO:
    low_supervision_capacity: int
    advance_payment_percentage: int
    appointment_buffer_time: int
    vip_monthly_price: Decimal

def get_global_settings() -> SettingsDTO:
    obj = GlobalSettings.load()
    return SettingsDTO(
        low_supervision_capacity=obj.low_supervision_capacity,
        advance_payment_percentage=obj.advance_payment_percentage,
        appointment_buffer_time=obj.appointment_buffer_time,
        vip_monthly_price=obj.vip_monthly_price,
    )

def get_setting(key: str, default=None):
    """
    Obtiene un setting específico sin cargar todo el objeto.
    Útil para optimizar queries.
    """
    try:
        settings = GlobalSettings.load()
        return getattr(settings, key, default)
    except Exception:
        return default

@transaction.atomic
def admin_flag_non_grata(admin_user, target_user, details: Optional[Dict[str, Any]] = None):
    """
    Registra en auditoría. El bloqueo efectivo del usuario lo hará la app 'users'.
    """
    AuditLog.objects.create(
        action=AuditLog.Action.FLAG_NON_GRATA,
        admin_user=admin_user,
        target_user=target_user,
        details=details or {},
    )
    return True
