#!/usr/bin/env python
"""
Simula exactamente lo que hace el frontend para debuggear
"""
import requests
import json

print("=" * 60)
print("SIMULACION EXACTA DEL REQUEST DEL FRONTEND")
print("=" * 60)

# PASO 1: Obtener token de admin (simula login)
print("\n[1] Obteniendo token de admin...")

login_response = requests.post(
    'http://localhost:8000/api/v1/auth/login/',
    json={
        'email': 'andrea.demo@studiozens.test',  # Usuario admin que encontramos
        'password': 'TU_PASSWORD_AQUI'  # Cambiar por el password correcto
    }
)

if login_response.status_code != 200:
    print(f"ERROR en login: {login_response.status_code}")
    print(f"Response: {login_response.text[:500]}")
    print("\nCambia el password en el script y vuelve a correr")
    exit(1)

token_data = login_response.json()
access_token = token_data.get('access')

print(f"Token obtenido: {access_token[:50]}...")

# PASO 2: Request al endpoint de ordenes (exactamente como lo hace el frontend)
print("\n[2] Haciendo GET /api/v1/marketplace/admin/orders/...")

headers = {
    'Authorization': f'Bearer {access_token}',
    'Content-Type': 'application/json'
}

# Sin filtro
response = requests.get(
    'http://localhost:8000/api/v1/marketplace/admin/orders/',
    headers=headers
)

print(f"\nStatus Code: {response.status_code}")
print(f"Content-Type: {response.headers.get('Content-Type')}")

if response.status_code == 200:
    data = response.json()
    print(f"\nTotal ordenes devueltas: {len(data)}")

    if isinstance(data, list):
        if len(data) > 0:
            print("\nPrimera orden:")
            print(json.dumps(data[0], indent=2, default=str))
        else:
            print("\nLISTA VACIA - No se devolvieron ordenes")
            print("Esto es lo que ve el frontend: []")
    else:
        print(f"\nRespuesta inesperada (no es lista): {type(data)}")
        print(json.dumps(data, indent=2, default=str))
else:
    print(f"\nERROR {response.status_code}:")
    try:
        error_data = response.json()
        print(json.dumps(error_data, indent=2))
    except:
        print(response.text[:1000])

# PASO 3: Con filtro status=PAID (como en el frontend)
print("\n" + "=" * 60)
print("[3] Haciendo GET /api/v1/marketplace/admin/orders/?status=PAID")
print("=" * 60)

response = requests.get(
    'http://localhost:8000/api/v1/marketplace/admin/orders/?status=PAID',
    headers=headers
)

print(f"\nStatus Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"Total ordenes PAID devueltas: {len(data)}")

    if len(data) > 0:
        print("\nOrden PAID:")
        order = data[0]
        print(json.dumps(order, indent=2, default=str))
    else:
        print("\nLISTA VACIA - No hay ordenes con status=PAID")
        print("PERO sabemos que SI hay 1 orden PAID en la DB...")
        print("\nPosibles causas:")
        print("1. El serializer no incluye la orden")
        print("2. El filtro por status no funciona")
        print("3. El queryset del ViewSet las excluye")
        print("4. Problema de permisos")
else:
    print(f"\nERROR {response.status_code}:")
    try:
        error_data = response.json()
        print(json.dumps(error_data, indent=2))
    except:
        print(response.text[:1000])

print("\n" + "=" * 60)
