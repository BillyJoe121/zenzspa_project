# Refactor Completo: core/models.py → core/models/

## ✅ Estado: 100% Completado

El archivo `core/models.py` (~508 líneas) ha sido refactorizado exitosamente en una estructura modular.

---

## 📁 Estructura de Archivos

```
core/models/
├── __init__.py          # Exportaciones para compatibilidad
├── base.py              # Modelos base y soft delete
├── audit.py             # Sistema de auditoría
├── settings.py          # Configuración global (singleton)
├── idempotency.py       # Claves de idempotencia
└── notifications.py     # Notificaciones administrativas
```

---

## 📄 Archivos Creados

### 1. **base.py** (Modelos Base)
**Responsabilidad**: Proveer modelos abstractos base y patrón de soft delete

**Clases exportadas**:
- `BaseModel`: Modelo abstracto con UUID, timestamps
- `SoftDeleteQuerySet`: QuerySet personalizado para soft delete
- `SoftDeleteManager`: Manager personalizado para soft delete
- `SoftDeleteModel`: Modelo abstracto con funcionalidad de borrado suave

**Uso típico**:
```python
from core.models import BaseModel, SoftDeleteModel

class MyModel(BaseModel):
    # Hereda id (UUID), created_at, updated_at
    name = models.CharField(max_length=100)

class MyDeletableModel(SoftDeleteModel):
    # Hereda BaseModel + deleted_at, is_deleted
    # Usa objects.all() para registros activos
    # Usa objects.with_deleted() para incluir eliminados
    pass
```

---

### 2. **audit.py** (Sistema de Auditoría)
**Responsabilidad**: Registro de acciones administrativas y del sistema

**Clases exportadas**:
- `AuditLog`: Modelo para registrar acciones administrativas

**Acciones registradas**:
- FLAG_NON_GRATA
- ADMIN_CANCEL_APPOINTMENT
- ADMIN_ENDPOINT_HIT
- APPOINTMENT_CANCELLED_BY_ADMIN
- SYSTEM_CANCEL
- APPOINTMENT_RESCHEDULE_FORCE
- APPOINTMENT_COMPLETED
- CLINICAL_PROFILE_ANONYMIZED
- VOUCHER_REDEEMED
- LOYALTY_REWARD_ISSUED
- VIP_DOWNGRADED
- MARKETPLACE_RETURN
- FINANCIAL_ADJUSTMENT_CREATED

**Uso típico**:
```python
from core.models import AuditLog

AuditLog.objects.create(
    admin_user=request.user,
    target_user=customer,
    action=AuditLog.Action.FLAG_NON_GRATA,
    details="Usuario bloqueado por comportamiento inapropiado"
)
```

---

### 3. **settings.py** (Configuración Global - Singleton)
**Responsabilidad**: Almacenar y gestionar configuraciones globales del sistema

**Clases exportadas**:
- `GlobalSettings`: Modelo singleton para configuración global
- `GLOBAL_SETTINGS_CACHE_KEY`: Clave de caché
- `GLOBAL_SETTINGS_SINGLETON_UUID`: UUID fijo del singleton

**Secciones de configuración**:
1. **Capacidad y Horarios**:
   - `low_supervision_capacity`
   - `appointment_buffer_time`
   - `timezone_display`

2. **Pagos y Anticipos**:
   - `advance_payment_percentage`
   - `advance_expiration_minutes`

3. **VIP y Suscripciones**:
   - `vip_monthly_price`
   - `loyalty_months_required`
   - `loyalty_voucher_service`

4. **Créditos**:
   - `credit_expiration_days`
   - `no_show_credit_policy` (NONE/PARTIAL/FULL)

5. **Marketplace**:
   - `return_window_days`

6. **Notificaciones**:
   - `quiet_hours_start`
   - `quiet_hours_end`

7. **Lista de Espera**:
   - `waitlist_enabled`
   - `waitlist_ttl_minutes`

8. **Desarrollador**:
   - `developer_commission_percentage`
   - `developer_payout_threshold`
   - `developer_in_default`
   - `developer_default_since`

**Uso típico**:
```python
from core.models import GlobalSettings

# Obtener configuración (desde caché o DB)
settings = GlobalSettings.load()

# Calcular anticipo
advance = appointment.total_price * (settings.advance_payment_percentage / 100)

# Verificar política de no-show
if settings.no_show_credit_policy == GlobalSettings.NoShowCreditPolicy.FULL:
    # Convertir todo el anticipo en crédito
    pass
```

**Características especiales**:
- Patrón Singleton con UUID fijo
- Caché automático en Redis/memoria
- Validaciones de dominio en `clean()`
- Logging de cambios críticos
- Prevención de race conditions con `select_for_update`
- Comisión del desarrollador solo puede incrementarse

---

### 4. **idempotency.py** (Claves de Idempotencia)
**Responsabilidad**: Gestionar claves de idempotencia para operaciones críticas

**Clases exportadas**:
- `IdempotencyKey`: Modelo para prevenir operaciones duplicadas

**Estados**:
- `PENDING`: Operación en proceso
- `COMPLETED`: Operación completada

**Uso típico**:
```python
from core.models import IdempotencyKey

# Crear clave de idempotencia
key = IdempotencyKey.objects.create(
    key=request.headers.get('Idempotency-Key'),
    user=request.user,
    endpoint='/api/payments/create',
    request_hash=hash_request(request.data)
)

# Marcar como en proceso
key.mark_processing()

try:
    # Realizar operación crítica
    result = process_payment(...)

    # Marcar como completado
    key.mark_completed(
        response_body={"status": "success"},
        status_code=200
    )
except Exception as e:
    # Manejar error
    pass
```

---

### 5. **notifications.py** (Notificaciones Administrativas)
**Responsabilidad**: Gestionar notificaciones para el panel administrativo

**Clases exportadas**:
- `AdminNotification`: Modelo para notificaciones del panel admin

**Tipos de notificación**:
- `PAGOS`: Notificaciones de pagos
- `SUSCRIPCIONES`: Notificaciones de suscripciones
- `USUARIOS`: Notificaciones de usuarios

**Subtipos**:
- `PAGO_EXITOSO`: Pago procesado correctamente
- `PAGO_FALLIDO`: Error en procesamiento de pago
- `USUARIO_CNG`: Usuario marcado como Persona Non Grata
- `USUARIO_RECURRENTE`: Usuario recurrente detectado
- `OTRO`: Otras notificaciones

**Uso típico**:
```python
from core.models import AdminNotification

AdminNotification.objects.create(
    title="Pago procesado",
    message=f"Usuario {user.phone_number} realizó pago de ${amount}",
    notification_type=AdminNotification.NotificationType.PAGOS,
    subtype=AdminNotification.NotificationSubtype.PAGO_EXITOSO
)

# Obtener notificaciones no leídas
unread = AdminNotification.objects.filter(is_read=False)
```

---

### 6. **__init__.py** (Exportaciones)
**Responsabilidad**: Mantener compatibilidad con imports existentes

**Exporta todos los modelos y constantes**:
```python
from core.models import (
    # Base
    BaseModel,
    SoftDeleteQuerySet,
    SoftDeleteManager,
    SoftDeleteModel,
    # Audit
    AuditLog,
    # Settings
    GlobalSettings,
    GLOBAL_SETTINGS_CACHE_KEY,
    GLOBAL_SETTINGS_SINGLETON_UUID,
    # Idempotency
    IdempotencyKey,
    # Notifications
    AdminNotification,
)
```

---

## ✅ Verificación de Compatibilidad

### Imports Verificados:
```bash
✅ Todos los imports de core.models funcionan correctamente
  - BaseModel: <class 'core.models.base.BaseModel'>
  - SoftDeleteModel: <class 'core.models.base.SoftDeleteModel'>
  - AuditLog: <class 'core.models.audit.AuditLog'>
  - GlobalSettings: <class 'core.models.settings.GlobalSettings'>
  - IdempotencyKey: <class 'core.models.idempotency.IdempotencyKey'>
  - AdminNotification: <class 'core.models.notifications.AdminNotification'>
  - GLOBAL_SETTINGS_CACHE_KEY: core:global_settings:v1
  - GLOBAL_SETTINGS_SINGLETON_UUID: 00000000-0000-0000-0000-000000000001
✅ Todas las clases tienen los atributos esperados
```

### Migraciones:
✅ No se generaron nuevas migraciones en la app `core`
✅ La estructura de base de datos permanece idéntica

---

## 📊 Métricas del Refactor

| Métrica | Valor |
|---------|-------|
| **Archivo original** | models.py (508 líneas) |
| **Archivos creados** | 6 archivos |
| **Líneas totales** | ~520 líneas (similar al original) |
| **Modelos refactorizados** | 5 modelos principales |
| **Constantes exportadas** | 2 constantes |
| **Compatibilidad** | 100% backward compatible |

---

## 🔄 Comparación con Original

### Antes:
```python
# Imports dispersos
from core.models import AuditLog, GlobalSettings, IdempotencyKey, AdminNotification, BaseModel
```

### Después:
```python
# Mismo import, estructura modular interna
from core.models import AuditLog, GlobalSettings, IdempotencyKey, AdminNotification, BaseModel
```

**Sin cambios necesarios en el código existente** ✅

---

## 📝 Notas Importantes

1. **Archivo original respaldado**: `core/models.py.old`
2. **Todos los imports existentes funcionan**: Sin cambios necesarios en código que usa estos modelos
3. **No hay nuevas migraciones**: La estructura de DB es idéntica
4. **Patrón seguido**: Similar a refactors anteriores (bot/views/webhook, spa/views/appointments, users/views)
5. **Singleton preservado**: GlobalSettings mantiene su UUID fijo y patrón singleton
6. **Caché preservado**: GlobalSettings continúa usando caché con la misma clave

---

## 🎯 Beneficios del Refactor

1. **Organización**: Cada modelo en su propio archivo por responsabilidad
2. **Mantenibilidad**: Más fácil encontrar y modificar modelos específicos
3. **Claridad**: Cada archivo tiene un propósito claro y documentado
4. **Escalabilidad**: Facilita agregar nuevos modelos sin saturar un archivo único
5. **Testing**: Más fácil escribir tests unitarios por modelo
6. **Compatibilidad**: Cero impacto en código existente

---

## 🚀 Refactor Completado - 100%

**Estado**: ✅ Producción Ready
**Fecha**: 2025-11-27
**Versión**: Django 5.1.4
