from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from core.utils.caching import CacheKeys
from .models import GlobalSettings


@receiver([post_save, post_delete], sender=GlobalSettings)
def invalidate_global_settings_cache(sender, **kwargs):
    """
    Invalida el caché de GlobalSettings cuando se modifica o elimina.
    Usa la misma llave que GlobalSettings.load() para asegurar consistencia.
    """
    cache.delete(CacheKeys.GLOBAL_SETTINGS)
