#!/usr/bin/env python
"""
Script para aplicar retroactivamente precios VIP a servicios y productos existentes.

Este script aplica el descuento del 15% a todos los servicios y productos
que no tengan precio VIP configurado.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from decimal import Decimal
from spa.models import Service
from marketplace.models import ProductVariant

# Descuento VIP (15%)
VIP_DISCOUNT = Decimal('0.15')


def apply_vip_prices_to_services():
    """Aplica precios VIP a todos los servicios existentes."""
    
    print("\n" + "=" * 70)
    print("APLICANDO PRECIOS VIP A SERVICIOS")
    print("=" * 70)
    
    services = Service.objects.all()
    updated_count = 0
    
    for service in services:
        if service.price is None:
            print(f"   ⚠️  {service.name}: Sin precio configurado, omitiendo...")
            continue
        
        # Calcular precio VIP
        vip_price = service.price * (Decimal('1') - VIP_DISCOUNT)
        vip_price = vip_price.quantize(Decimal('0.01'))
        
        # Solo actualizar si no tiene precio VIP o es diferente
        if service.vip_price != vip_price:
            old_vip = service.vip_price or "No configurado"
            service.vip_price = vip_price
            service.save(update_fields=['vip_price'])
            
            print(f"   ✓ {service.name}")
            print(f"      Precio regular: ${service.price}")
            print(f"      VIP anterior: {old_vip}")
            print(f"      VIP nuevo: ${vip_price}")
            print(f"      Ahorro: ${service.price - vip_price}")
            print()
            
            updated_count += 1
    
    print(f"\n   Total servicios actualizados: {updated_count}/{services.count()}")
    return updated_count


def apply_vip_prices_to_products():
    """Aplica precios VIP a todas las variantes de productos existentes."""
    
    print("\n" + "=" * 70)
    print("APLICANDO PRECIOS VIP A PRODUCTOS")
    print("=" * 70)
    
    variants = ProductVariant.objects.select_related('product').all()
    updated_count = 0
    
    for variant in variants:
        if variant.price is None:
            print(f"   ⚠️  {variant.product.name} ({variant.name}): Sin precio, omitiendo...")
            continue
        
        # Calcular precio VIP
        vip_price = variant.price * (Decimal('1') - VIP_DISCOUNT)
        vip_price = vip_price.quantize(Decimal('0.01'))
        
        # Solo actualizar si no tiene precio VIP o es diferente
        if variant.vip_price != vip_price:
            old_vip = variant.vip_price or "No configurado"
            variant.vip_price = vip_price
            variant.save(update_fields=['vip_price'])
            
            print(f"   ✓ {variant.product.name} - {variant.name}")
            print(f"      SKU: {variant.sku}")
            print(f"      Precio regular: ${variant.price}")
            print(f"      VIP anterior: {old_vip}")
            print(f"      VIP nuevo: ${vip_price}")
            print(f"      Ahorro: ${variant.price - vip_price}")
            print()
            
            updated_count += 1
    
    print(f"\n   Total variantes actualizadas: {updated_count}/{variants.count()}")
    return updated_count


def main():
    """Ejecuta la aplicación de precios VIP."""
    
    print("\n" + "=" * 70)
    print("APLICACIÓN RETROACTIVA DE PRECIOS VIP")
    print("Descuento: 15% sobre precio regular")
    print("=" * 70)
    
    # Aplicar a servicios
    services_updated = apply_vip_prices_to_services()
    
    # Aplicar a productos
    products_updated = apply_vip_prices_to_products()
    
    # Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    print(f"   Servicios actualizados: {services_updated}")
    print(f"   Productos actualizados: {products_updated}")
    print(f"   Total: {services_updated + products_updated}")
    print("\n✅ Aplicación completada exitosamente!")
    print("\n📝 NOTA: A partir de ahora, todos los nuevos servicios y productos")
    print("   tendrán su precio VIP calculado automáticamente al crearlos.")
    print("=" * 70)


if __name__ == '__main__':
    main()
