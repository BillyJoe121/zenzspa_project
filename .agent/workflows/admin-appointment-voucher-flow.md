---
description: Plan de implementación para creación de citas por admin con vouchers
---

# Plan de Implementación: Creación de Citas por Admin con Vouchers

## Estado Actual

### ✅ Ya Implementado:
1. **Búsqueda de clientes por teléfono**: `GET /api/v1/auth/admin/users/search-by-phone/?phone=...`
2. **Creación de citas por admin**: `POST /api/appointments/admin-create/`
3. **Recepción de anticipo en persona**: `POST /api/appointments/{id}/receive-advance-in-person/`
4. **Sistema de Vouchers y Créditos**: Modelos `Voucher`, `Package`, `ClientCredit`

### ❌ Pendiente de Implementar:

## Fase 1: Backend - Búsqueda de Clientes

### 1.1 Ampliar búsqueda de clientes
**Archivo**: `users/views/admin_views.py`

Modificar el endpoint `search-by-phone` para que también busque por nombre:
- Cambiar nombre a `search-clients`
- Aceptar parámetro `query` que busque en: `phone_number`, `first_name`, `last_name`
- Mantener compatibilidad con parámetro `phone` existente

```python
@action(detail=False, methods=['get'], url_path='search-clients')
def search_clients(self, request):
    """
    Busca clientes por teléfono o nombre.
    
    GET /api/v1/auth/admin/users/search-clients/?query=...
    """
    query = request.query_params.get('query', '').strip()
    # Buscar en phone_number, first_name, last_name
```

## Fase 2: Backend - Gestión de Vouchers del Cliente

### 2.1 Endpoint para listar vouchers disponibles de un cliente
**Archivo**: `spa/views/voucher_admin.py` (o crear nuevo viewset)

```python
GET /api/v1/vouchers/client/{client_id}/available/
```

Retorna:
- Vouchers disponibles del cliente
- Agrupados por servicio
- Con fecha de expiración

### 2.2 Endpoint para crear voucher manual
**Archivo**: `spa/views/voucher_admin.py`

```python
POST /api/v1/vouchers/create-manual/
{
    "client_id": "uuid",
    "service_id": "uuid",
    "expires_at": "2025-12-31" (opcional)
}
```

## Fase 3: Backend - Modificar Creación de Citas

### 3.1 Actualizar serializer de creación de citas por admin
**Archivo**: `spa/serializers/appointment.py`

Modificar `AdminAppointmentCreateSerializer` para incluir:
```python
payment_method = serializers.ChoiceField(
    choices=['VOUCHER', 'CREDIT', 'PAYMENT_LINK', 'CASH'],
    default='PAYMENT_LINK'
)
voucher_id = serializers.UUIDField(required=False, allow_null=True)
```

### 3.2 Modificar lógica de creación de citas
**Archivo**: `spa/views/appointments/appointment_viewset.py`

Actualizar `admin_create_for_client` para:
1. Validar si se usa voucher
2. Si usa voucher:
   - Marcar voucher como USED
   - Crear pago con estado PAID_WITH_CREDIT
   - Confirmar cita inmediatamente
   - Enviar notificación de "cita confirmada"
3. Si usa crédito:
   - Aplicar crédito disponible
   - Si cubre el total, confirmar cita
   - Si no cubre, generar link de pago por diferencia
4. Si es pago en línea:
   - Flujo actual (generar link de Wompi)
5. Si es efectivo:
   - Marcar como pendiente de pago en persona

### 3.3 Lógica de uso de vouchers
**Archivo**: `spa/services/vouchers.py` (revisar si existe)

Crear servicio para:
```python
def use_voucher_for_appointment(voucher, appointment):
    """
    Marca un voucher como usado y lo asocia a una cita.
    Crea un pago con estado PAID_WITH_CREDIT.
    """
```

## Fase 4: Notificaciones

### 4.1 Crear template de notificación para cita con voucher
**Archivo**: `notifications/templates/` (verificar ubicación)

Template: `ADMIN_APPOINTMENT_CREATED_WITH_VOUCHER`
- Mensaje: "Tu cita ha sido agendada y confirmada usando tu voucher"
- No incluir link de pago
- Incluir detalles de la cita

### 4.2 Modificar notificación de pago
Actualizar `ADMIN_APPOINTMENT_PAYMENT_LINK` para:
- Diferenciar entre anticipo total y anticipo parcial (cuando se usa crédito)
- Mostrar monto exacto a pagar

## Fase 5: Frontend (Opcional - si se requiere)

### 5.1 Página de creación de citas por admin
**Ruta**: `/admin/appointments/create`

Flujo:
1. Buscar cliente (por nombre o teléfono)
2. Seleccionar servicio(s)
3. Seleccionar staff (si aplica)
4. Ver calendario y seleccionar fecha
5. Ver horarios disponibles y seleccionar hora
6. **NUEVO**: Pantalla de método de pago:
   - Opción: Usar voucher existente (mostrar lista)
   - Opción: Crear voucher nuevo
   - Opción: Usar crédito disponible
   - Opción: Generar link de pago
   - Opción: Pago en efectivo
7. Confirmar y crear cita

## Endpoints Finales

```
# Búsqueda de clientes
GET /api/v1/auth/admin/users/search-clients/?query={nombre_o_telefono}

# Vouchers del cliente
GET /api/v1/vouchers/client/{client_id}/available/
POST /api/v1/vouchers/create-manual/

# Créditos del cliente
GET /api/v1/finances/credits/client/{client_id}/

# Crear cita (modificado)
POST /api/appointments/admin-create/
{
    "client_id": "uuid",
    "service_ids": ["uuid"],
    "staff_member_id": "uuid",
    "start_time": "ISO datetime",
    "payment_method": "VOUCHER|CREDIT|PAYMENT_LINK|CASH",
    "voucher_id": "uuid" (si payment_method=VOUCHER),
    "send_whatsapp": true
}
```

## Orden de Implementación Recomendado

1. ✅ Ampliar búsqueda de clientes (Backend)
2. ✅ Endpoint de vouchers disponibles (Backend)
3. ✅ Modificar serializer de creación de citas (Backend)
4. ✅ Actualizar lógica de creación de citas con vouchers (Backend)
5. ✅ Crear/actualizar notificaciones (Backend)
6. ✅ Testing de endpoints
7. 🔄 Frontend (si se requiere interfaz visual)

## Notas Técnicas

- El sistema de vouchers ya existe en `spa/models/voucher.py`
- El sistema de créditos ya existe en `finances/models.py`
- La creación de citas por admin ya existe en `appointment_viewset.py`
- Solo falta integrar vouchers/créditos en el flujo de creación
