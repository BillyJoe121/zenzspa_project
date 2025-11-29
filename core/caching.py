"""
Claves de caché centralizadas para todo el sistema.

Este módulo define todas las claves de caché utilizadas en la aplicación
de forma centralizada para evitar duplicación y facilitar el mantenimiento.
"""
from dataclasses import dataclass


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
