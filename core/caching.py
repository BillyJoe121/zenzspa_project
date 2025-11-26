from dataclasses import dataclass

@dataclass(frozen=True)
class CacheKeys:
    SERVICES = "catalog:services:v1"
    CATEGORIES = "catalog:categories:v1"
    PACKAGES = "catalog:packages:v1"
    GLOBAL_SETTINGS = "core:global_settings:v1"  # Sincronizado con GLOBAL_SETTINGS_CACHE_KEY en models.py
