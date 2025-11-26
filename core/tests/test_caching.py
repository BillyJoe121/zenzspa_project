from core.caching import CacheKeys


def test_cache_keys_constants_exist():
    assert CacheKeys.SERVICES == "catalog:services:v1"
    assert CacheKeys.CATEGORIES == "catalog:categories:v1"
    assert CacheKeys.PACKAGES == "catalog:packages:v1"
    assert CacheKeys.GLOBAL_SETTINGS == "core:global_settings:v1"
