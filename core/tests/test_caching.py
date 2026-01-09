
import pytest
from unittest.mock import patch
from core.utils.caching import CacheKeys, acquire_lock, GLOBAL_SETTINGS_CACHE_KEY

def test_cache_keys_constants():
    assert CacheKeys.GLOBAL_SETTINGS == "core:global_settings:v1"
    assert CacheKeys.SERVICES == "catalog:services:v1"
    assert CacheKeys.CATEGORIES == "catalog:categories:v1"
    assert CacheKeys.PACKAGES == "catalog:packages:v1"
    assert GLOBAL_SETTINGS_CACHE_KEY == CacheKeys.GLOBAL_SETTINGS

@patch('core.caching.cache')
def test_acquire_lock_success(mock_cache):
    mock_cache.add.return_value = True
    assert acquire_lock('test_lock') is True
    mock_cache.add.assert_called_once_with('lock:test_lock', True, timeout=5)

@patch('core.caching.cache')
def test_acquire_lock_failure(mock_cache):
    mock_cache.add.return_value = False
    assert acquire_lock('test_lock') is False

@patch('core.caching.cache')
def test_acquire_lock_exception(mock_cache):
    mock_cache.add.side_effect = Exception("Redis down")
    assert acquire_lock('test_lock') is False
