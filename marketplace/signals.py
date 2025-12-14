"""
Signals para calcular automáticamente precios VIP en productos.

Este módulo aplica automáticamente un descuento del 15% al precio VIP
cada vez que se crea o actualiza una variante de producto.
"""
from decimal import Decimal
from django.db.models.signals import pre_save
from django.dispatch import receiver

from marketplace.models import ProductVariant

# Descuento VIP global (15%)
VIP_DISCOUNT_PERCENTAGE = Decimal('0.15')


@receiver(pre_save, sender=ProductVariant)
def calculate_vip_price_for_product_variant(sender, instance, **kwargs):
    """
    Calcula automáticamente el precio VIP para variantes de productos.

    Aplica un descuento del 15% sobre el precio regular.
    Solo se ejecuta si:
    - La variante tiene un precio definido
    - El precio VIP no ha sido establecido manualmente

    IMPORTANTE: Si ya existe un vip_price establecido explícitamente,
    este signal NO lo sobrescribirá, permitiendo precios VIP personalizados.
    """
    if instance.price is None:
        return

    # Calcular precio VIP (85% del precio regular)
    calculated_vip_price = instance.price * (Decimal('1') - VIP_DISCOUNT_PERCENTAGE)
    calculated_vip_price = calculated_vip_price.quantize(Decimal('0.01'))

    # Solo aplicar si no existe precio VIP
    if instance.vip_price is None:
        instance.vip_price = calculated_vip_price
    else:
        # Verificar si el precio regular cambió Y si el VIP actual es el calculado automáticamente
        # (esto permite detectar si el VIP fue personalizado)
        if instance.pk:
            try:
                old_instance = ProductVariant.objects.get(pk=instance.pk)
                # Calcular el VIP esperado del precio anterior
                old_expected_vip = (old_instance.price * (Decimal('1') - VIP_DISCOUNT_PERCENTAGE)).quantize(Decimal('0.01'))

                # Si el precio regular cambió Y el VIP actual es el esperado (no personalizado),
                # entonces recalcular
                if old_instance.price != instance.price and old_instance.vip_price == old_expected_vip:
                    instance.vip_price = calculated_vip_price
                # Si el VIP actual NO es el esperado, significa que fue personalizado,
                # por lo tanto NO lo tocamos
            except ProductVariant.DoesNotExist:
                # Nueva variante, solo aplicar si vip_price es None
                pass
