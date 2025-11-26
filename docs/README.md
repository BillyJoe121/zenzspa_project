# Core Module Documentation

## Descripción General

El módulo `core` es la columna vertebral del sistema ZenzSpa, proporcionando modelos base, utilidades compartidas, decoradores, middleware, permisos y configuraciones globales utilizadas por todos los demás módulos.

---

## 📦 Componentes Principales

### 1. **BaseModel**

Modelo abstracto base que proporciona campos comunes a todos los modelos del sistema.

**Campos**:
- `id`: UUID primary key (auto-generado)
- `created_at`: Timestamp de creación (auto)
- `updated_at`: Timestamp de última modificación (auto)

**Uso**:
```python
from core.models import BaseModel

class MyModel(BaseModel):
    name = models.CharField(max_length=100)
    # Automáticamente tendrá id, created_at, updated_at
```

---

### 2. **SoftDeleteModel**

Extiende `BaseModel` con funcionalidad de soft delete (eliminación lógica).

**Campos adicionales**:
- `is_deleted`: Boolean flag
- `deleted_at`: Timestamp de eliminación

**Managers**:
- `objects`: Solo objetos no eliminados (default)
- `all_objects`: Todos los objetos (incluidos eliminados)

**Métodos**:
- `delete()`: Soft delete (marca como eliminado)
- `hard_delete()`: Eliminación permanente de DB
- `restore()`: Restaurar objeto eliminado

**Uso**:
```python
from core.models import SoftDeleteModel

class Product(SoftDeleteModel):
    name = models.CharField(max_length=100)

# Soft delete
product.delete()  # is_deleted=True, deleted_at=now()

# Restaurar
product.restore()  # is_deleted=False, deleted_at=None

# Hard delete (permanente)
product.hard_delete()

# Queries
Product.objects.all()  # Solo no eliminados
Product.all_objects.all()  # Todos
Product.objects.dead()  # Solo eliminados
```

---

### 3. **GlobalSettings**

Modelo Singleton para configuración global del sistema. Se cachea automáticamente.

**⚠️ IMPORTANTE**: Siempre usar `GlobalSettings.load()`, nunca `get()` o `filter()`.

**Campos principales**:
- `advance_payment_percentage`: % de anticipo requerido
- `low_supervision_capacity`: Capacidad máxima para servicios de baja supervisión
- `appointment_buffer_time`: Tiempo de limpieza entre citas (minutos)
- `vip_monthly_price`: Precio mensual VIP
- `developer_commission_percentage`: Comisión del desarrollador (solo puede aumentar)
- `timezone_display`: Zona horaria del sistema
- Y más...

**Uso**:
```python
from core.models import GlobalSettings

# Obtener configuraciones
settings = GlobalSettings.load()  # Siempre usar load()
advance_percentage = settings.advance_payment_percentage

# Modificar
settings.advance_payment_percentage = 25
settings.save()  # Invalida caché automáticamente

# Obtener un setting específico (optimizado)
from core.services import get_setting
percentage = get_setting('advance_payment_percentage', default=20)
```

**Validaciones**:
- `advance_payment_percentage`: 0-100
- `low_supervision_capacity`: >= 1
- `developer_commission_percentage`: Solo puede mantenerse o incrementarse
- `timezone_display`: Debe ser un timezone válido

---

### 4. **IdempotencyKey**

Modelo para prevenir requests duplicados usando claves de idempotencia.

**Campos**:
- `key`: Clave única (min 16 caracteres)
- `user`: Usuario que hizo el request
- `endpoint`: Endpoint llamado
- `status`: PENDING | COMPLETED
- `request_hash`: Hash SHA256 del request body
- `response_body`: Respuesta almacenada
- `status_code`: Código HTTP de respuesta
- `locked_at`: Timestamp de bloqueo
- `completed_at`: Timestamp de completado

**Uso con decorator**:
```python
from core.decorators import idempotent_view
from rest_framework.decorators import action

class OrderViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    @idempotent_view(timeout=60)
    def create_order(self, request):
        # Cliente debe enviar header: Idempotency-Key: <uuid>
        # Si se reenvía el mismo request, retorna la respuesta cacheada
        return Response({"order_id": "123"})
```

**Limpieza automática**:
- Claves completadas > 7 días: Eliminadas
- Claves pendientes > 24 horas: Eliminadas (posibles fallos)
- Ejecuta diariamente vía Celery Beat

---

### 5. **AuditLog**

Registro de auditoría para acciones administrativas críticas.

**Acciones soportadas**:
- `FLAG_NON_GRATA`: Marcar usuario como persona no grata
- `ADMIN_CANCEL_APPOINTMENT`: Admin cancela cita
- `APPOINTMENT_COMPLETED`: Cita completada
- `CLINICAL_PROFILE_ANONYMIZED`: Perfil clínico anonimizado
- Y más...

**Uso**:
```python
from core.models import AuditLog

AuditLog.objects.create(
    action=AuditLog.Action.FLAG_NON_GRATA,
    admin_user=admin,
    target_user=client,
    details="Razón del bloqueo"
)
```

---

## 🔐 Permissions

### **IsAdmin**
Solo usuarios con `role=ADMIN`.

```python
from core.permissions import IsAdmin

class AdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAdmin]
```

### **IsStaff**
Usuarios con `role=STAFF` o `role=ADMIN`.

```python
from core.permissions import IsStaff

class StaffViewSet(viewsets.ViewSet):
    permission_classes = [IsStaff]
```

### **RoleAllowed**
Flexible, define `required_roles` en la vista.

```python
from core.permissions import RoleAllowed

class MyViewSet(viewsets.ViewSet):
    permission_classes = [RoleAllowed]
    required_roles = {"CLIENT", "VIP"}  # Solo estos roles
```

**Validación automática**: Si defines roles inválidos, se loggea error y se niega acceso.

---

## 🎨 Serializers

### **DataMaskingMixin**

Mixin para enmascarar datos sensibles según el rol del usuario.

```python
from core.serializers import DataMaskingMixin

class UserSerializer(DataMaskingMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number']
        mask_fields = {
            "phone_number": {
                "mask_with": "phone",  # +57300****567
                "visible_for": ["STAFF", "ADMIN"]
            },
            "email": {
                "mask_with": "email",  # j***@example.com
                "visible_for": ["STAFF", "ADMIN"]
            },
        }
```

---

## 🛡️ Logging Filters

### **SanitizeAPIKeyFilter**

Filtra API keys, tokens y secretos de los logs.

**Patrones detectados**:
- API keys (GEMINI_API_KEY, etc.)
- Tokens de autorización
- Claves en URLs (query params)
- Claves en JSON

### **SanitizePIIFilter**

Filtra información personal identificable (PII).

**Patrones detectados**:
- Números de teléfono
- Emails
- Números de documento
- Números de tarjeta de crédito

**Configuración en settings.py**:
```python
LOGGING = {
    'filters': {
        'sanitize_api_keys': {
            '()': 'core.logging_filters.SanitizeAPIKeyFilter',
        },
        'sanitize_pii': {
            '()': 'core.logging_filters.SanitizePIIFilter',
        },
    },
    'handlers': {
        'console': {
            'filters': ['sanitize_api_keys', 'sanitize_pii'],
        },
    },
}
```

---

## ⚡ Throttling

### **AdminThrottle**

Rate limiting específico para endpoints administrativos.

```python
from core.throttling import AdminThrottle

class AdminViewSet(viewsets.ViewSet):
    throttle_classes = [AdminThrottle]  # 1000/hour
```

**Configuración en settings.py**:
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'admin': '1000/hour',
        'burst_anon': '20/min',
        'sustained_anon': '200/hour',
        'burst_user': '60/min',
        'login': '5/min',
    }
}
```

---

## 🔧 Utilidades

### **get_client_ip(request)**

Obtiene la IP real del cliente, considerando proxies.

```python
from core.utils import get_client_ip

ip = get_client_ip(request)
```

### **safe_audit_log(...)**

Crea log de auditoría con manejo de errores.

```python
from core.utils import safe_audit_log

safe_audit_log(
    action=AuditLog.Action.FLAG_NON_GRATA,
    admin_user=admin,
    target_user=client,
    details="Razón"
)
```

---

## 📊 Tareas Celery

### **cleanup_old_idempotency_keys**

Limpia claves de idempotencia antiguas.

**Configuración en Celery Beat**:
```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-idempotency-keys': {
        'task': 'core.tasks.cleanup_old_idempotency_keys',
        'schedule': crontab(hour=3, minute=0),  # 3 AM diario
    },
}
```

---

## 🧪 Testing

Ejecutar tests del módulo core:

```bash
pytest core/tests.py -v
```

**Cobertura de tests**:
- GlobalSettings (singleton, caché, validaciones)
- IdempotencyKey (creación, limpieza)
- AuditLog (creación)
- Permissions (validación de roles)
- SoftDeleteModel (soft delete, restore)

---

## 🚨 Mejoras Implementadas

### Críticas (Implementadas)
1. ✅ Race condition en GlobalSettings.load() - Usa select_for_update
2. ✅ Limpieza automática de IdempotencyKey - Tarea Celery
3. ✅ Validación de hash en idempotent_view - Previene reutilización con datos diferentes
4. ✅ Índices en IdempotencyKey - Performance mejorada
5. ✅ SoftDeleteModel.delete() atómico - Previene race conditions
6. ✅ Validación de formato en logging filters - Manejo de errores
7. ✅ Validación de roles en RoleAllowed - Previene configuraciones inválidas
8. ✅ Suite de tests completa - Cobertura básica implementada

### Importantes (Implementadas)
9. ✅ Logging en GlobalSettings.save() - Audita cambios críticos
10. ✅ Validación de longitud en IdempotencyKey.key - Mínimo 16 caracteres
11. ✅ AdminThrottle - Rate limiting para admins
12. ✅ Sanitización de tarjetas en logs - PII protegida
13. ✅ Validación de timezone - Previene timezones inválidos
14. ✅ get_setting() - Optimización de queries

---

## 📝 Próximos Pasos

1. Crear migración para nuevos índices: `python manage.py makemigrations core`
2. Aplicar migración: `python manage.py migrate core`
3. Configurar Celery Beat para limpieza automática
4. Ejecutar tests: `pytest core/tests.py -v`
5. Aumentar cobertura de tests a 80%+

---

## 🔗 Referencias

- [Django Models Best Practices](https://docs.djangoproject.com/en/stable/topics/db/models/)
- [DRF Permissions](https://www.django-rest-framework.org/api-guide/permissions/)
- [Celery Beat](https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html)
