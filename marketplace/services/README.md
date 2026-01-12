# Módulo Marketplace Services - Refactorización en Progreso

## Estado Actual

El archivo `marketplace/services.py` (~619 líneas) está siendo refactorizado en una estructura modular.

## Estructura Planificada

```
marketplace/services/
├── __init__.py              # Exporta todos los servicios
├── README.md                # Este archivo
├── notifications.py         # MarketplaceNotificationService
├── inventory.py             # InventoryService
├── order_creation.py        # OrderCreationService
├── order_management.py      # OrderService (líneas 268-481)
└── returns.py               # ReturnService (líneas 482-619)
```

## Servicios Identificados

### 1. MarketplaceNotificationService (líneas 19-148)
**Responsabilidad**: Envío de notificaciones del marketplace
- `send_order_status_update()`: Notifica cambios de estado de orden
- `send_low_stock_alert()`: Alerta a admins de stock bajo
- `send_return_processed()`: Notifica devoluciones procesadas

### 2. InventoryService (líneas 150-157)
**Responsabilidad**: Gestión de inventario
- `check_low_stock()`: Verifica y alerta stock bajo

### 3. OrderCreationService (líneas 159-266)
**Responsabilidad**: Creación de órdenes desde carrito
- `__init__()`: Constructor con user, cart, data
- `create_order()`: Crea orden atómicamente
  - Valida carrito no vacío
  - Crea orden inicial
  - Calcula fecha estimada de entrega
  - Procesa ítems del carrito
  - Reserva stock
  - Registra movimientos de inventario
  - Vacía el carrito

### 4. OrderService (líneas 268-481)
**Responsabilidad**: Gestión del ciclo de vida de órdenes
- Transiciones de estado
- Confirmación de pagos
- Envíos y entregas
- Cancelaciones
- Gestión de auditoría

### 5. ReturnService (líneas 482-619)
**Responsabilidad**: Gestión de devoluciones
- Procesamiento de returns
- Generación de créditos
- Restauración de stock
- Notificaciones de devolución

## Dependencias Identificadas

### Modelos
- `Order`, `OrderItem`, `ProductVariant`, `InventoryMovement` (marketplace.models)
- `ClientCredit` (spa.models)
- `AuditLog`, `GlobalSettings` (core.models)
- `BotConfiguration` (bot.models)
- `CustomUser` (users.models)

### Servicios
- `NotificationService` (notifications.services)
- `notify_order_status_change` (marketplace.tasks - Celery)

### Excepciones
- `BusinessLogicError` (core.exceptions)

## Estado de Implementación

### ✅ Completado
- Análisis de estructura
- Identificación de servicios
- Documentación de responsabilidades
- Creación de carpeta `marketplace/services/`

### 🔄 Pendiente
- Crear `notifications.py` con MarketplaceNotificationService
- Crear `inventory.py` con InventoryService
- Crear `order_creation.py` con OrderCreationService
- Crear `order_management.py` con OrderService
- Crear `returns.py` con ReturnService
- Crear `__init__.py` con exportaciones
- Actualizar imports en:
  - `marketplace/views.py`
  - `marketplace/tasks.py`
  - Tests de marketplace
- Ejecutar tests de validación
- Renombrar archivo original a `services.py.old`

## Notas Técnicas

### Transaccionalidad
- `OrderCreationService.create_order()` usa `@transaction.atomic`
- Los servicios utilizan `select_for_update()` para evitar race conditions

### Sistema de Stock
- Stock reservado vs stock disponible
- Movimientos de inventario rastreados en `InventoryMovement`
- Alertas automáticas cuando stock < threshold

### Notificaciones
- Integrado con sistema centralizado `NotificationService`
- Event codes: `ORDER_SHIPPED`, `ORDER_DELIVERED`, `ORDER_READY_FOR_PICKUP`, `STOCK_LOW_ALERT`, `ORDER_CREDIT_ISSUED`

### Auditoría
- Cambios de estado registrados en `AuditLog`
- Tracking de quién realizó cada acción

## Próximos Pasos

1. Extraer cada clase a su archivo correspondiente
2. Ajustar imports relativos (`..models`, `..tasks`)
3. Crear `__init__.py` con todas las exportaciones
4. Actualizar imports en archivos dependientes
5. Ejecutar suite completa de tests
6. Validar que no hay regresiones
