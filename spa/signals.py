"""
Signals para calcular automáticamente precios VIP.

Este módulo aplica automáticamente un descuento del 15% al precio VIP
cada vez que se crea o actualiza un servicio.
"""
from decimal import Decimal
from django.db.models.signals import pre_save
from django.dispatch import receiver

from spa.models import Service

# Descuento VIP global (15%)
VIP_DISCOUNT_PERCENTAGE = Decimal('0.15')


@receiver(pre_save, sender=Service)
def calculate_vip_price_for_service(sender, instance, **kwargs):
    """
    Calcula automáticamente el precio VIP para servicios.
    
    Aplica un descuento del 15% sobre el precio regular.
    Solo se ejecuta si:
    - El servicio tiene un precio definido
    - El precio VIP no ha sido establecido manualmente o ha cambiado el precio regular
    """
    if instance.price is None:
        return
    
    # Calcular precio VIP (85% del precio regular)
    calculated_vip_price = instance.price * (Decimal('1') - VIP_DISCOUNT_PERCENTAGE)
    calculated_vip_price = calculated_vip_price.quantize(Decimal('0.01'))
    
    # Si no existe precio VIP o el precio regular cambió, recalcular
    if instance.vip_price is None:
        instance.vip_price = calculated_vip_price
    else:
        # Verificar si el precio regular cambió
        if instance.pk:
            try:
                old_instance = Service.objects.get(pk=instance.pk)
                # Si el precio regular cambió, recalcular el VIP
                if old_instance.price != instance.price:
                    instance.vip_price = calculated_vip_price
            except Service.DoesNotExist:
                # Nuevo servicio, aplicar precio VIP calculado
                instance.vip_price = calculated_vip_price
