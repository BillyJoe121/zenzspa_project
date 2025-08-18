from __future__ import annotations
from typing import Any, Callable, Optional, TypeVar, Tuple
from functools import lru_cache, wraps
from django.utils.timezone import now
from django.core.cache import cache
from django.http import HttpRequest
from zoneinfo import ZoneInfo

T = TypeVar("T")

BOGOTA_TZ = ZoneInfo("America/Bogota")

def utc_now():
    return now()

def to_bogota(dt):
    if not dt:
        return dt
    return dt.astimezone(BOGOTA_TZ)

def get_client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")

def cached_singleton(key: str, timeout: int, loader: Callable[[], T]) -> T:
    value = cache.get(key)
    if value is None:
        value = loader()
        cache.set(key, value, timeout=timeout)
    return value

def invalidate(key: str):
    cache.delete(key)

def safe_audit_log(action: str, admin_user=None, target_user=None, target_appointment=None, details: Any = None):
    """
    Escribe AuditLog tolerante a errores y a importaciones circulares.
    """
    try:
        from .models import AuditLog  # import local para evitar ciclos
        entry = AuditLog.objects.create(
            action=action,
            admin_user=admin_user,
            target_user=target_user,
            target_appointment=target_appointment,
            details=details or "",
        )
        return entry
    except Exception:
        return None
