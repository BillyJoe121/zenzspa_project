#!/usr/bin/env python
"""
Script de debugging para el endpoint admin-create de citas.
Ejecutar: python manage.py shell < debug_admin_create.py
"""

import json
from datetime import datetime, timedelta
from django.utils import timezone
from users.models import CustomUser
from spa.models import Service
from spa.serializers.appointment import AdminAppointmentCreateSerializer

print("=" * 80)
print("DEBUG: Endpoint POST /api/appointments/admin-create/")
print("=" * 80)

# 1. Verificar que existan clientes
print("\n1. Verificando clientes disponibles...")
clients = CustomUser.objects.filter(
    role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP],
    is_active=True,
    is_persona_non_grata=False
)[:5]

if not clients:
    print("❌ No hay clientes disponibles")
else:
    print(f"✅ Encontrados {clients.count()} clientes:")
    for client in clients:
        print(f"   - {client.id} | {client.first_name} {client.last_name} | {client.phone_number}")

# 2. Verificar que existan servicios
print("\n2. Verificando servicios disponibles...")
services = Service.objects.filter(is_active=True)[:5]

if not services:
    print("❌ No hay servicios disponibles")
else:
    print(f"✅ Encontrados {services.count()} servicios:")
    for service in services:
        print(f"   - {service.id} | {service.name} | {service.duration}min | ${service.price}")

# 3. Verificar que exista staff
print("\n3. Verificando staff disponible...")
staff = CustomUser.objects.filter(
    role__in=[CustomUser.Role.STAFF, CustomUser.Role.ADMIN],
    is_active=True
)[:5]

if not staff:
    print("❌ No hay staff disponible")
else:
    print(f"✅ Encontrados {staff.count()} staff:")
    for s in staff:
        print(f"   - {s.id} | {s.first_name} {s.last_name} | {s.role}")

# 4. Probar serializer con datos válidos
print("\n4. Probando serializer con datos de prueba...")

if clients and services:
    client = clients.first()
    service = services.first()
    
    # Crear payload de prueba
    start_time = timezone.now() + timedelta(days=1)
    start_time = start_time.replace(hour=15, minute=0, second=0, microsecond=0)
    
    payload = {
        'client_id': str(client.id),
        'service_ids': [str(service.id)],
        'start_time': start_time,
        'payment_method': 'PAYMENT_LINK',
        'send_whatsapp': False  # Desactivar para prueba
    }
    
    # Si el servicio requiere staff, agregarlo
    if not service.category.is_low_supervision and staff:
        payload['staff_member_id'] = str(staff.first())
    
    print(f"\nPayload de prueba:")
    print(json.dumps({
        'client_id': payload['client_id'],
        'service_ids': payload['service_ids'],
        'staff_member_id': payload.get('staff_member_id'),
        'start_time': payload['start_time'].isoformat(),
        'payment_method': payload['payment_method'],
        'send_whatsapp': payload['send_whatsapp']
    }, indent=2))
    
    # Validar con serializer
    serializer = AdminAppointmentCreateSerializer(data=payload)
    
    if serializer.is_valid():
        print("\n✅ Serializer válido!")
        print(f"Validated data keys: {list(serializer.validated_data.keys())}")
    else:
        print("\n❌ Errores de validación:")
        print(json.dumps(serializer.errors, indent=2))
else:
    print("❌ No se pueden crear datos de prueba (faltan clientes o servicios)")

# 5. Verificar configuración de payment_method
print("\n5. Verificando valores válidos de payment_method...")
valid_methods = ['VOUCHER', 'CREDIT', 'PAYMENT_LINK', 'CASH']
print(f"Valores válidos: {valid_methods}")

# 6. Verificar formato de fecha
print("\n6. Verificando formato de fecha...")
now = timezone.now()
future = now + timedelta(days=1, hours=3)
future_rounded = future.replace(minute=0, second=0, microsecond=0)

print(f"Ahora: {now.isoformat()}")
print(f"Futuro (válido): {future_rounded.isoformat()}")
print(f"Formato correcto: YYYY-MM-DDTHH:MM:SS")

# 7. Verificar intervalos de 15 minutos
print("\n7. Verificando intervalos de 15 minutos...")
valid_minutes = [0, 15, 30, 45]
print(f"Minutos válidos: {valid_minutes}")
print(f"Ejemplo válido: 2025-12-25T15:00:00")
print(f"Ejemplo inválido: 2025-12-25T15:05:00")

print("\n" + "=" * 80)
print("FIN DEL DEBUG")
print("=" * 80)
