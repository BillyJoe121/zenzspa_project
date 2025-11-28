# Módulo Core Models - Refactorización

## Estado Actual

El archivo `core/models.py` (~508 líneas) está siendo refactorizado en una estructura modular.

## Estructura Planificada

```
core/models/
├── __init__.py          # Exporta todos los modelos
├── README.md            # Este archivo
├── base.py             # ✅ BaseModel, SoftDelete* (líneas 19-119)
├── audit.py            # AuditLog (líneas 122-183)
├── settings.py         # GlobalSettings (líneas 184-417)
├── idempotency.py      # IdempotencyKey (líneas 418-474)
└── notifications.py    # AdminNotification (líneas 475-508)
```

## Modelos Identificados

### ✅ 1. base.py - Modelos Base (COMPLETADO)
**Líneas**: 19-119 del original

**Clases**:
- `BaseModel(models.Model)`: Modelo abstracto base
  - UUID como PK
  - `created_at`, `updated_at` automáticos
  - Ordenamiento por `-created_at`

- `SoftDeleteQuerySet(models.QuerySet)`: QuerySet personalizado
  - `delete()`: Soft delete
  - `hard_delete()`: Eliminación permanente
  - `alive()`: Registros no eliminados
  - `dead()`: Registros eliminados

- `SoftDeleteManager(models.Manager)`: Manager personalizado
  - `include_deleted` parameter
  - Filtra automáticamente registros eliminados
  - `hard_delete()` method

- `SoftDeleteModel(BaseModel)`: Modelo abstracto con soft delete
  - Campos: `is_deleted`, `deleted_at`
  - Managers: `objects`, `all_objects`
  - Métodos: `delete()`, `hard_delete()`, `restore()`
  - Manejo atómico de race conditions

### 2. audit.py - Registro de Auditoría
**Líneas**: 122-183 del original

**Modelo**: `AuditLog(BaseModel)`
- Registro de acciones administrativas y del sistema
- Campos:
  - `admin_user`: Usuario que realizó la acción (FK a CustomUser)
  - `target_user`: Usuario afectado (FK a CustomUser)
  - `target_appointment`: Cita relacionada (FK a Appointment)
  - `action`: Tipo de acción (TextChoices)
  - `details`: Detalles de la acción
  - `metadata`: JSONField para datos adicionales

**Actions**:
- USER_CREATED, USER_UPDATED, USER_DELETED
- APPOINTMENT_CREATED, APPOINTMENT_CANCELLED_BY_ADMIN
- FLAG_NON_GRATA, SYSTEM_CANCEL
- PAYMENT_CONFIRMED, CREDIT_GENERATED

### 3. settings.py - Configuración Global
**Líneas**: 184-417 del original

**Modelo**: `GlobalSettings(BaseModel)`
- Singleton para configuración global de la aplicación
- UUID fijo: `00000000-0000-0000-0000-000000000001`
- Cache key: `core:global_settings:v1`

**Configuraciones**:
- **Operación**:
  - `timezone`: Zona horaria (default: America/Bogota)
  - `business_hours_start`, `business_hours_end`
  - `days_of_week` (JSON): Días operativos

- **Reservas**:
  - `advance_booking_days`: Días máximos de anticipación
  - `min_booking_hours`: Horas mínimas de anticipación
  - `cancellation_window_hours`: Ventana de cancelación

- **Pagos**:
  - `deposit_percentage`: Porcentaje de depósito
  - `require_payment_at_booking`: Requiere pago al reservar

- **Créditos**:
  - `credit_validity_days`: Días de validez de créditos
  - `no_show_credit_policy`: Política de crédito por no-show
    - NONE, HALF, FULL

- **Marketplace**:
  - `marketplace_enabled`: Habilitar marketplace
  - `allow_guest_checkout`: Permitir compra sin registro

- **Notificaciones**:
  - `send_email_notifications`, `send_sms_notifications`
  - `send_whatsapp_notifications`

- **Lista de Espera**:
  - `waitlist_enabled`: Habilitar lista de espera
  - `waitlist_offer_timeout_hours`: Timeout de ofertas

**Métodos**:
- `load()`: Carga singleton con cache
- `clear_cache()`: Limpia cache
- `save()`: Guarda y limpia cache
- `get_business_timezone()`: Obtiene ZoneInfo

### 4. idempotency.py - Idempotencia
**Líneas**: 418-474 del original

**Modelo**: `IdempotencyKey(BaseModel)`
- Control de idempotencia para requests
- Previene procesamiento duplicado de operaciones

**Campos**:
- `key`: Clave única (max_length=255, unique, indexed)
- `user`: Usuario asociado (FK a CustomUser, nullable)
- `endpoint`: Endpoint de la operación
- `request_data`: JSONField con datos del request
- `response_data`: JSONField con respuesta
- `response_status_code`: Código de estado HTTP
- `is_processed`: Si fue procesada
- `processed_at`: Timestamp de procesamiento

**Meta**:
- Índices: `key`, `user`
- Ordenamiento: `-created_at`

**Métodos**:
- `mark_processed()`: Marca como procesada
- `__str__()`: Representación como string

### 5. notifications.py - Notificaciones Admin
**Líneas**: 475-508 del original

**Modelo**: `AdminNotification(BaseModel)`
- Notificaciones para panel administrativo

**Campos**:
- `title`: Título (max_length=255)
- `message`: Mensaje
- `notification_type`: Tipo (TextChoices)
  - USUARIOS, CITAS, PAGOS, SISTEMA, MARKETPLACE
- `subtype`: Subtipo (TextChoices)
  - USUARIO_NUEVO, USUARIO_CNG
  - CITA_NUEVA, CITA_CANCELADA
  - PAGO_CONFIRMADO, PAGO_FALLIDO
  - STOCK_BAJO, NUEVA_ORDEN
- `is_read`: Si fue leída
- `read_at`: Timestamp de lectura
- `read_by`: Usuario que leyó (FK a CustomUser)
- `priority`: Prioridad (low, medium, high)
- `metadata`: JSONField para datos adicionales

**Métodos**:
- `mark_as_read()`: Marca como leída

## Constantes Globales

```python
GLOBAL_SETTINGS_CACHE_KEY = "core:global_settings:v1"
GLOBAL_SETTINGS_SINGLETON_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
```

## Estado de Implementación

### ✅ Completado
- Análisis de estructura (100%)
- Documentación completa
- Creación de carpeta `core/models/`
- `base.py` con BaseModel y SoftDelete (100%)

### 🔄 Pendiente
- Crear `audit.py` con AuditLog
- Crear `settings.py` con GlobalSettings y constantes
- Crear `idempotency.py` con IdempotencyKey
- Crear `notifications.py` con AdminNotification
- Crear `__init__.py` con todas las exportaciones
- Actualizar imports en:
  - Todos los modelos que heredan de BaseModel
  - Todas las apps que usan AuditLog
  - Todas las apps que usan GlobalSettings
  - Admin, serializers, views, services
- Verificar migraciones (importante)
- Ejecutar tests de validación
- Renombrar archivo original a `models.py.old`

## Impacto en Migraciones

⚠️ **IMPORTANTE**: Este refactor NO debe generar nuevas migraciones ya que:
- Los modelos no cambian su estructura
- Solo se reorganizan en archivos diferentes
- Las importaciones se mantienen compatibles vía `__init__.py`

## Dependencias

### Imports Internos
- `users.models.CustomUser` (ForeignKeys en AuditLog, AdminNotification, IdempotencyKey)
- `spa.models.Appointment` (ForeignKey en AuditLog)

### Paquetes Django
- `django.db.models`
- `django.core.cache`
- `django.core.exceptions`
- `django.utils.timezone`
- `zoneinfo.ZoneInfo`

## Próximos Pasos

1. Completar archivos restantes (audit, settings, idempotency, notifications)
2. Crear `__init__.py` que exporte TODO
3. Verificar que no haya imports circulares
4. Ejecutar `python manage.py makemigrations` - NO debe crear migraciones
5. Ejecutar tests completos
6. Buscar y reemplazar todos los imports de `core.models`
7. Validar admin panel
