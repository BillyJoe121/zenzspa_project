from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from spa.models import Appointment, Payment
from marketplace.models import Order


@receiver([post_save, post_delete], sender=Payment)
def invalidate_payment_analytics_cache(sender, instance, **kwargs):
    """
    Invalida el caché de analytics cuando se crea, actualiza o elimina un pago.
    """
    # Invalidar KPIs y time series que dependen de pagos
    cache.delete_pattern('analytics:kpis:*')
    cache.delete_pattern('analytics:timeseries:*')
    cache.delete_pattern('analytics:dataset:*')
    cache.delete_pattern('analytics:bi:*')  # BI metrics también usan pagos


@receiver([post_save, post_delete], sender=Appointment)
def invalidate_appointment_analytics_cache(sender, instance, **kwargs):
    """
    Invalida el caché de analytics cuando se crea, actualiza o elimina una cita.
    """
    # Invalidar KPIs, time series y ops que dependen de citas
    cache.delete_pattern('analytics:kpis:*')
    cache.delete_pattern('analytics:timeseries:*')
    cache.delete_pattern('analytics:dataset:*')
    cache.delete_pattern('analytics:ops:*')  # Operational insights usan citas


@receiver([post_save, post_delete], sender=Order)
def invalidate_order_analytics_cache(sender, instance, **kwargs):
    """
    Invalida el caché de analytics cuando se crea, actualiza o elimina una orden.
    """
    # Invalidar métricas de marketplace
    cache.delete_pattern('analytics:kpis:*')
    cache.delete_pattern('analytics:bi:inventory:*')
