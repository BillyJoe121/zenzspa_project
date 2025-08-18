from dataclasses import dataclass

@dataclass(frozen=True)
class CacheKeys:
    SERVICES = "catalog:services:v1"
    CATEGORIES = "catalog:categories:v1"
    PACKAGES = "catalog:packages:v1"
    GLOBAL_SETTINGS = "global_settings"
