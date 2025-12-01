"""
Claves de caché centralizadas y utilidades básicas de locking.
"""
from dataclasses import dataclass
from django.core.cache import cache


@dataclass(frozen=True)
class CacheKeys:
    """
    Contenedor inmutable de todas las claves de caché del sistema.

    Uso:
        from core.caching import CacheKeys
        cache.get(CacheKeys.GLOBAL_SETTINGS)
    """
    # Configuración global
    GLOBAL_SETTINGS = "core:global_settings:v1"

    # Catálogo de servicios
    SERVICES = "catalog:services:v1"
    CATEGORIES = "catalog:categories:v1"
    PACKAGES = "catalog:packages:v1"


# Alias para retrocompatibilidad
GLOBAL_SETTINGS_CACHE_KEY = CacheKeys.GLOBAL_SETTINGS


def acquire_lock(key: str, timeout: int = 5) -> bool:
    """
    Intenta adquirir un lock distribuido usando cache.add (SETNX).
    Devuelve True si se adquiere, False en caso contrario.
    """
    try:
        return cache.add(f"lock:{key}", True, timeout=timeout)
    except Exception:
        return False
