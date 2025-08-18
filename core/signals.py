from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import GlobalSettings

@receiver([post_save, post_delete], sender=GlobalSettings)
def invalidate_global_settings_cache(sender, **kwargs):
    cache.delete("global_settings")
