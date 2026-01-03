#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from django.test import Client
from users.models import CustomUser
from rest_framework.authtoken.models import Token

print("=" * 60)
print("TEST ENDPOINT ADMIN ORDERS")
print("=" * 60)

# Buscar un usuario admin
admin_user = CustomUser.objects.filter(role='ADMIN').first()

if not admin_user:
    print("\nNo hay usuarios ADMIN en la base de datos.")
    print("Creando usuario admin de prueba...")
    admin_user = CustomUser.objects.create_user(
        email='admin@test.com',
        password='admin123',
        role='ADMIN',
        is_staff=True,
        is_superuser=True
    )
    print(f"Usuario admin creado: {admin_user.email}")
else:
    print(f"\nUsuario admin encontrado: {admin_user.email}")

# Obtener o crear token
from rest_framework_simplejwt.tokens import RefreshToken
refresh = RefreshToken.for_user(admin_user)
access_token = str(refresh.access_token)

print(f"\nToken generado (primeros 50 chars): {access_token[:50]}...")

# Hacer request al endpoint
client = Client()

print("\n" + "-" * 60)
print("Test 1: GET /api/v1/marketplace/admin/orders/")
print("-" * 60)

response = client.get(
    '/api/v1/marketplace/admin/orders/',
    HTTP_AUTHORIZATION=f'Bearer {access_token}'
)

print(f"\nStatus Code: {response.status_code}")
print(f"Content-Type: {response.get('Content-Type')}")

if response.status_code == 200:
    import json
    data = response.json()
    print(f"\nTotal ordenes devueltas: {len(data)}")

    if len(data) > 0:
        print("\nPrimera orden:")
        print(json.dumps(data[0], indent=2, default=str))
    else:
        print("\nNo se devolvieron ordenes (lista vacia)")
else:
    print(f"\nError: {response.content.decode()[:500]}")

print("\n" + "-" * 60)
print("Test 2: GET /api/v1/marketplace/admin/orders/?status=PAID")
print("-" * 60)

response = client.get(
    '/api/v1/marketplace/admin/orders/?status=PAID',
    HTTP_AUTHORIZATION=f'Bearer {access_token}'
)

print(f"\nStatus Code: {response.status_code}")

if response.status_code == 200:
    import json
    data = response.json()
    print(f"Total ordenes PAID devueltas: {len(data)}")

    if len(data) > 0:
        print("\nOrden PAID encontrada:")
        order = data[0]
        print(f"  ID: {order.get('id', 'N/A')}")
        print(f"  Status: {order.get('status', 'N/A')}")
        print(f"  Total: ${order.get('total_amount', 'N/A')}")
        print(f"  Usuario: {order.get('user', 'N/A')}")
    else:
        print("\nNo se devolvieron ordenes PAID")
else:
    print(f"\nError: {response.content.decode()[:500]}")

print("\n" + "=" * 60)
