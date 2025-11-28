# Refactor Completo: marketplace/services.py → marketplace/services/

## ✅ Estado: 100% Completado

El archivo `marketplace/services.py` (~620 líneas) ha sido refactorizado exitosamente en una estructura modular.

---

## 📁 Estructura de Archivos

```
marketplace/services/
├── __init__.py                  # Exportaciones para compatibilidad
├── notification_service.py      # Servicio de notificaciones
├── inventory_service.py         # Gestión de inventario
├── order_creation_service.py    # Creación de órdenes
├── order_service.py             # Transiciones de estado de órdenes
└── return_service.py            # Gestión de devoluciones
```

---

## 📄 Archivos Creados

### 1. **notification_service.py** (Servicio de Notificaciones)
**Responsabilidad**: Gestionar notificaciones relacionadas con marketplace

**Clases exportadas**:
- `MarketplaceNotificationService`: Servicio de notificaciones para el módulo Marketplace

**Métodos principales**:
- `send_order_status_update(order, new_status)`: Envía notificación de cambio de estado de orden
- `send_low_stock_alert(variants)`: Envía alerta de stock bajo a administradores
- `send_return_processed(order, amount)`: Envía notificación de devolución procesada

**Uso típico**:
```python
from marketplace.services import MarketplaceNotificationService

# Notificar cambio de estado
MarketplaceNotificationService.send_order_status_update(
    order=order,
    new_status=Order.OrderStatus.SHIPPED
)

# Alerta de stock bajo
MarketplaceNotificationService.send_low_stock_alert([variant])

# Notificar devolución procesada
MarketplaceNotificationService.send_return_processed(order, amount=50000)
```

**Eventos soportados**:
- `ORDER_SHIPPED`: Orden enviada
- `ORDER_DELIVERED`: Orden entregada
- `ORDER_READY_FOR_PICKUP`: Orden lista para recoger
- `STOCK_LOW_ALERT`: Alerta de stock bajo
- `ORDER_CREDIT_ISSUED`: Crédito emitido por devolución

---

### 2. **inventory_service.py** (Gestión de Inventario)
**Responsabilidad**: Verificar niveles de stock y generar alertas

**Clases exportadas**:
- `InventoryService`: Servicio de gestión de inventario

**Métodos principales**:
- `check_low_stock(variant)`: Verifica si una variante está bajo el umbral de stock

**Uso típico**:
```python
from marketplace.services import InventoryService

# Verificar stock después de una venta
InventoryService.check_low_stock(variant)
```

---

### 3. **order_creation_service.py** (Creación de Órdenes)
**Responsabilidad**: Encapsular la lógica de creación de órdenes desde carritos

**Clases exportadas**:
- `OrderCreationService`: Servicio para crear órdenes a partir de carritos

**Métodos principales**:
- `create_order()`: Crea una orden de forma atómica con validaciones

**Proceso de creación**:
1. Validar carrito no vacío
2. Crear orden inicial
3. Calcular fecha estimada de entrega
4. Iterar sobre ítems del carrito
5. Bloquear variantes con `select_for_update`
6. Validar stock disponible
7. Aplicar precios (VIP o regular)
8. Reservar stock temporalmente
9. Crear registros de `InventoryMovement`
10. Vaciar carrito

**Uso típico**:
```python
from marketplace.services import OrderCreationService

# Crear servicio
service = OrderCreationService(
    user=request.user,
    cart=cart,
    data={
        'delivery_option': 'DELIVERY',
        'delivery_address': 'Calle 123',
    }
)

# Crear orden atómicamente
order = service.create_order()
```

**Características**:
- Operación atómica con `@transaction.atomic`
- Bloqueo pesimista para evitar race conditions
- Reserva temporal de stock (30 minutos)
- Precios VIP automáticos si aplica
- Registro completo de movimientos de inventario

---

### 4. **order_service.py** (Gestión de Estado de Órdenes)
**Responsabilidad**: Manejar transiciones de estado con validaciones estrictas

**Clases exportadas**:
- `OrderService`: Servicio para gestionar el ciclo de vida de órdenes

**Métodos principales**:
- `transition_to(order, new_status, changed_by)`: Cambia el estado de una orden
- `confirm_payment(order, paid_amount)`: Confirma el pago de una orden
- `release_reservation(order, movement_type, reason, changed_by)`: Libera reserva de stock
- `_validate_pricing(order)`: Valida que los precios sigan vigentes
- `_capture_stock(order)`: Captura stock reservado al confirmar pago

**Transiciones permitidas**:
```python
ALLOWED_TRANSITIONS = {
    PENDING_PAYMENT → PAID, CANCELLED, FRAUD_ALERT
    PAID → PREPARING, CANCELLED, RETURN_REQUESTED
    PREPARING → SHIPPED, CANCELLED
    SHIPPED → DELIVERED, RETURN_REQUESTED
    DELIVERED → RETURN_REQUESTED
    RETURN_REQUESTED → RETURN_APPROVED, RETURN_REJECTED
    RETURN_APPROVED → REFUNDED
}
```

**Uso típico**:
```python
from marketplace.services import OrderService

# Transicionar estado
OrderService.transition_to(
    order=order,
    new_status=Order.OrderStatus.PREPARING,
    changed_by=request.user
)

# Confirmar pago
OrderService.confirm_payment(
    order=order,
    paid_amount=Decimal('50000.00')
)

# Liberar reserva
OrderService.release_reservation(
    order=order,
    movement_type=InventoryMovement.MovementType.RESERVATION_RELEASE,
    reason="Reserva expirada",
    changed_by=None
)
```

**Validaciones**:
- Transiciones de estado válidas
- Validación de precios al confirmar pago
- Validación de monto pagado vs total de orden
- Stock suficiente para captura
- Manejo de reservas expiradas

---

### 5. **return_service.py** (Gestión de Devoluciones)
**Responsabilidad**: Procesar solicitudes y aprobaciones de devoluciones

**Clases exportadas**:
- `ReturnService`: Servicio para gestionar devoluciones

**Métodos principales**:
- `request_return(order, items, reason)`: Solicita devolución de ítems
- `process_return(order, approved, processed_by)`: Procesa aprobación/rechazo de devolución

**Proceso de devolución**:
1. **Solicitud** (`request_return`):
   - Validar estado de orden (PAID o DELIVERED)
   - Validar ventana de devoluciones (configurada en GlobalSettings)
   - Validar ítems a devolver
   - Cambiar estado a RETURN_REQUESTED
   - Notificar al staff

2. **Procesamiento** (`process_return`):
   - Si rechazada: cambiar a RETURN_REJECTED
   - Si aprobada:
     - Transicionar a RETURN_APPROVED
     - Devolver stock al inventario
     - Crear movimiento de inventario tipo RETURN
     - Crear crédito para el usuario
     - Registrar en audit log
     - Transicionar a REFUNDED
     - Notificar al usuario

**Uso típico**:
```python
from marketplace.services import ReturnService

# Solicitar devolución
order = ReturnService.request_return(
    order=order,
    items=[
        {'order_item_id': str(item1.id), 'quantity': 1},
        {'order_item_id': str(item2.id), 'quantity': 2},
    ],
    reason="Producto defectuoso"
)

# Procesar devolución (aprobada)
order = ReturnService.process_return(
    order=order,
    approved=True,
    processed_by=admin_user
)

# Procesar devolución (rechazada)
order = ReturnService.process_return(
    order=order,
    approved=False,
    processed_by=admin_user
)
```

**Validaciones**:
- Ventana de devoluciones (días configurables en GlobalSettings)
- Estado de orden válido para devolución
- Ítems válidos y cantidades correctas
- Orden debe estar entregada
- Cantidad a devolver no puede exceder lo comprado

**Características**:
- Operación atómica con `@transaction.atomic`
- Registro de auditoría para trazabilidad
- Creación automática de crédito con fecha de expiración
- Notificaciones automáticas al usuario
- Devolución parcial de ítems soportada

---

### 6. **__init__.py** (Exportaciones)
**Responsabilidad**: Mantener compatibilidad con imports existentes

**Exporta todos los servicios**:
```python
from marketplace.services import (
    MarketplaceNotificationService,
    InventoryService,
    OrderCreationService,
    OrderService,
    ReturnService,
)
```

---

## ✅ Verificación de Compatibilidad

### Imports Verificados:
```bash
✅ Todos los imports de marketplace.services funcionan correctamente
  - MarketplaceNotificationService: <class 'marketplace.services.notification_service.MarketplaceNotificationService'>
  - InventoryService: <class 'marketplace.services.inventory_service.InventoryService'>
  - OrderCreationService: <class 'marketplace.services.order_creation_service.OrderCreationService'>
  - OrderService: <class 'marketplace.services.order_service.OrderService'>
  - ReturnService: <class 'marketplace.services.return_service.ReturnService'>
✅ Todas las clases tienen los métodos esperados
```

### Migraciones:
```bash
No changes detected in app 'marketplace'
```

✅ No se generaron nuevas migraciones
✅ La estructura de base de datos permanece idéntica

---

## 📊 Métricas del Refactor

| Métrica | Valor |
|---------|-------|
| **Archivo original** | services.py (620 líneas) |
| **Archivos creados** | 6 archivos |
| **Líneas totales** | ~630 líneas (similar al original) |
| **Servicios refactorizados** | 5 servicios principales |
| **Compatibilidad** | 100% backward compatible |

---

## 🔄 Comparación con Original

### Antes:
```python
# Imports dispersos
from marketplace.services import OrderService, ReturnService, OrderCreationService
```

### Después:
```python
# Mismo import, estructura modular interna
from marketplace.services import OrderService, ReturnService, OrderCreationService
```

**Sin cambios necesarios en el código existente** ✅

---

## 📝 Notas Importantes

1. **Archivo original respaldado**: `marketplace/services.py.old`
2. **Todos los imports existentes funcionan**: Sin cambios necesarios en código que usa estos servicios
3. **No hay nuevas migraciones**: La estructura de DB es idéntica
4. **Patrón seguido**: Similar a refactors anteriores (bot/views/webhook, spa/views/appointments, users/views, core/models)
5. **Transacciones atómicas preservadas**: Todos los servicios mantienen `@transaction.atomic`
6. **Bloqueos pesimistas preservados**: `select_for_update()` se mantiene donde corresponde

---

## 🎯 Beneficios del Refactor

1. **Separación de responsabilidades**: Cada servicio en su propio archivo
2. **Mantenibilidad**: Más fácil encontrar y modificar lógica específica
3. **Claridad**: Cada archivo tiene un propósito claro
4. **Testing**: Más fácil escribir tests unitarios por servicio
5. **Reutilización**: Servicios pueden importarse selectivamente
6. **Escalabilidad**: Facilita agregar nuevos servicios sin saturar un archivo único
7. **Compatibilidad**: Cero impacto en código existente

---

## 🔗 Dependencias entre Servicios

```
┌─────────────────────────────────┐
│ MarketplaceNotificationService  │
└─────────────────────────────────┘
            ↑
            │ (usa)
┌─────────────────────────────────┐
│      InventoryService           │
└─────────────────────────────────┘
            ↑
            │ (usa)
┌─────────────────────────────────┐
│       OrderService              │
└─────────────────────────────────┘
            ↑
            │ (usa)
┌─────────────────────────────────┐
│      ReturnService              │
└─────────────────────────────────┘
```

---

## 🚀 Refactor Completado - 100%

**Estado**: ✅ Producción Ready
**Fecha**: 2025-11-27
**Versión**: Django 5.1.4
