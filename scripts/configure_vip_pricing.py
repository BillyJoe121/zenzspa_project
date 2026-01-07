#!/usr/bin/env python
"""
Script para configurar precios VIP.
DEPRECADO: Usar el panel de administración para cambiar el porcentaje de descuento.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from spa.services.pricing import update_service_vip_prices

def configure_vip_pricing():
    print("=" * 60)
    print("ACTUALIZACIÓN DE PRECIOS VIP (SCRIPT DEPRECADO)")
    print("=" * 60)
    print("Este script ahora ejecuta la lógica centralizada del sistema.")
    print("Por favor configura el porcentaje desde el panel de administración.")
    
    updated_count = update_service_vip_prices()
    
    print(f"\n✅ Se actualizaron {updated_count} servicios con el porcentaje configurado en GlobalSettings.")
    print("=" * 60)

if __name__ == '__main__':
    configure_vip_pricing()
