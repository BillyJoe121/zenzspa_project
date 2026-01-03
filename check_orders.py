#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from marketplace.models import Order

print("=" * 60)
print("DIAGNOSTICO DE ORDENES")
print("=" * 60)

total = Order.objects.count()
print(f"\nTotal ordenes en DB: {total}")

if total == 0:
    print("\nNo hay ordenes en la base de datos.")
    print("Necesitas crear ordenes de prueba primero.")
else:
    print(f"\nOrdenes por estado:")
    from django.db.models import Count
    statuses = Order.objects.values('status').annotate(count=Count('id')).order_by('-count')
    for s in statuses:
        print(f"   - {s['status']}: {s['count']}")

    print(f"\nUltimas 5 ordenes:")
    orders = Order.objects.select_related('user').order_by('-created_at')[:5]
    for order in orders:
        print(f"\n   ID: {str(order.id)[:8]}...")
        print(f"   Estado: {order.status}")
        print(f"   Usuario: {order.user.email}")
        print(f"   Total: ${order.total_amount}")
        print(f"   Fecha: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Items: {order.items.count()}")

print("\n" + "=" * 60)
