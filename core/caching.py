from dataclasses import dataclass

from .models import GLOBAL_SETTINGS_CACHE_KEY

@dataclass(frozen=True)
class CacheKeys:
    SERVICES = "catalog:services:v1"
    CATEGORIES = "catalog:categories:v1"
    PACKAGES = "catalog:packages:v1"
    GLOBAL_SETTINGS = GLOBAL_SETTINGS_CACHE_KEY
