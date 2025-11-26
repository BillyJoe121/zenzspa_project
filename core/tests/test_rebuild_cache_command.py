"""
Tests para validar que el comando rebuild_cache limpia las llaves correctas.
Específicamente, valida el fix para CORE-CACHE-KEY-DRIFT.
"""
import pytest
from io import StringIO
from django.core.cache import cache
from django.core.management import call_command

from core.models import GlobalSettings, GLOBAL_SETTINGS_CACHE_KEY
from core.caching import CacheKeys


@pytest.mark.django_db
class TestRebuildCacheCommand:
    """Tests para el comando rebuild_cache"""

    def test_rebuild_cache_clears_global_settings_cache(self):
        """El comando debe limpiar la clave correcta de GlobalSettings"""
        # Arrange: Cargar GlobalSettings para que se cachee
        settings = GlobalSettings.load()
        assert cache.get(GLOBAL_SETTINGS_CACHE_KEY) is not None

        # Act: Ejecutar rebuild_cache
        out = StringIO()
        call_command('rebuild_cache', stdout=out)

        # Assert: La clave correcta debe estar limpia
        assert cache.get(GLOBAL_SETTINGS_CACHE_KEY) is None
        assert "core:global_settings:v1" in out.getvalue()

    def test_rebuild_cache_uses_cachekeys_constants(self):
        """El comando debe usar las constantes de CacheKeys"""
        # Arrange: Cachear algunos valores
        cache.set(CacheKeys.SERVICES, "services_data", 300)
        cache.set(CacheKeys.CATEGORIES, "categories_data", 300)
        cache.set(CacheKeys.PACKAGES, "packages_data", 300)
        cache.set(CacheKeys.GLOBAL_SETTINGS, "settings_data", 300)

        # Act: Ejecutar rebuild_cache
        out = StringIO()
        call_command('rebuild_cache', stdout=out)

        # Assert: Todas las claves deben estar limpias
        assert cache.get(CacheKeys.SERVICES) is None
        assert cache.get(CacheKeys.CATEGORIES) is None
        assert cache.get(CacheKeys.PACKAGES) is None
        assert cache.get(CacheKeys.GLOBAL_SETTINGS) is None

    def test_rebuild_cache_after_global_settings_modification(self):
        """
        Validar que después de rebuild_cache, GlobalSettings.load()
        retorna valores actualizados desde la DB.
        """
        # Arrange: Cargar y modificar GlobalSettings
        settings = GlobalSettings.load()
        original_percentage = settings.advance_payment_percentage

        # Modificar directamente en DB (sin pasar por save que actualiza caché)
        GlobalSettings.objects.filter(pk=settings.pk).update(
            advance_payment_percentage=99
        )

        # Act: rebuild_cache debe limpiar el caché
        call_command('rebuild_cache', stdout=StringIO())

        # Assert: El siguiente load() debe traer el valor actualizado desde DB
        fresh_settings = GlobalSettings.load()
        assert fresh_settings.advance_payment_percentage == 99

        # Cleanup
        fresh_settings.advance_payment_percentage = original_percentage
        fresh_settings.save()
