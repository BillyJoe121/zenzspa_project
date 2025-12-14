#!/usr/bin/env python
"""
Script para configurar el precio VIP y aplicar descuentos del 15% a todos los servicios.

Configuración:
- Precio mensual VIP: $39,900 COP
- Descuento VIP: 15% sobre todos los servicios y productos
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from core.models.settings import GlobalSettings
from spa.models import Service


def configure_vip_pricing():
    """Configura el precio VIP mensual y aplica descuentos a servicios."""

    print("=" * 60)
    print("CONFIGURACIÓN DE PRECIOS VIP")
    print("=" * 60)

    # 1. Configurar precio mensual VIP
    print("\n1. Configurando precio mensual VIP...")
    settings = GlobalSettings.load()
    settings.vip_monthly_price = Decimal('39900.00')
    settings.save()
    print(f"   ✓ Precio VIP mensual: ${settings.vip_monthly_price} COP")

    # 2. Aplicar descuento del 15% a todos los servicios
    print("\n2. Aplicando descuento del 15% a servicios...")
    services = Service.objects.filter(is_active=True)
    discount_percentage = Decimal('0.15')  # 15%

    updated_count = 0
    for service in services:
        # Calcular precio VIP (85% del precio regular)
        vip_price = service.price * (Decimal('1') - discount_percentage)
        vip_price = vip_price.quantize(Decimal('0.01'))  # Redondear a 2 decimales

        # Actualizar solo si cambió
        if service.vip_price != vip_price:
            service.vip_price = vip_price
            service.save(update_fields=['vip_price'])
            updated_count += 1

            print(f"   ✓ {service.name}")
            print(f"      Precio regular: ${service.price}")
            print(f"      Precio VIP: ${vip_price} (ahorro: ${service.price - vip_price})")

    print(f"\n   Total servicios actualizados: {updated_count}")

    # 3. Resumen
    print("\n" + "=" * 60)
    print("RESUMEN DE CONFIGURACIÓN")
    print("=" * 60)
    print(f"Precio mensual VIP: ${settings.vip_monthly_price} COP")
    print(f"Descuento VIP: 15% en todos los servicios")
    print(f"Servicios con precio VIP: {updated_count}")

    # Calcular punto de equilibrio
    if services.exists():
        avg_price = services.aggregate(avg=models.Avg('price'))['avg']
        avg_vip_price = avg_price * (Decimal('1') - discount_percentage)
        avg_savings = avg_price - avg_vip_price

        break_even_services = (settings.vip_monthly_price / avg_savings).quantize(Decimal('0.01'))

        print(f"\nPunto de equilibrio:")
        print(f"  - Ahorro promedio por servicio: ${avg_savings}")
        print(f"  - Servicios necesarios para recuperar membresía: ~{int(break_even_services) + 1}")

    print("\n✅ Configuración completada exitosamente!")
    print("=" * 60)


if __name__ == '__main__':
    from django.db import models
    configure_vip_pricing()
