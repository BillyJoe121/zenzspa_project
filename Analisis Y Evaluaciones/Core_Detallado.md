# 🔍 ANÁLISIS DETALLADO DE MEJORAS - MÓDULO CORE
## Análisis Pre-Producción Completo

**Fecha de Análisis**: 2025-11-23  
**Analista**: Antigravity AI  
**Módulo**: `core/`  
**Total de Mejoras Identificadas**: 30+

---

## 📋 RESUMEN EJECUTIVO

El módulo `core` es la **columna vertebral del sistema**, proporcionando modelos base, excepciones, decoradores, middleware, permisos, serializers avanzados, y utilidades compartidas. El análisis identificó **30+ mejoras** organizadas en 6 categorías:

- 🔴 **8 Críticas** - Implementar antes de producción
- 🟡 **14 Importantes** - Primera iteración post-producción  
- 🟢 **8 Mejoras** - Implementar según necesidad

### Componentes Analizados (19 archivos)
- **Modelos**: BaseModel, SoftDeleteModel, GlobalSettings, AuditLog, IdempotencyKey, AdminNotification
- **Infraestructura**: Decorators, Middleware, Logging Filters, Exceptions
- **Seguridad**: Permissions, Data Masking, Sanitization
- **Utilidades**: Serializers, Services, Utils, Validators, Caching, Pagination, Throttling

### Áreas de Mayor Riesgo
1. **GlobalSettings sin validación de concurrencia** - Race conditions
2. **IdempotencyKey sin limpieza automática** - Crecimiento infinito de DB
3. **Testing completamente ausente** - Sin cobertura
4. **Falta de índices en modelos críticos** - Performance degradada
5. **Sanitización de PII demasiado agresiva** - Falsos positivos

---

## 🔴 CRÍTICAS (8) - Implementar Antes de Producción

### **1. Race Condition en GlobalSettings.load()**
**Severidad**: CRÍTICA  
**Ubicación**: `models.py` líneas 316-331  
**Código de Error**: `CORE-SETTINGS-RACE`

**Problema**: `get_or_create` sin lock permite crear múltiples instancias simultáneamente, violando el patrón singleton.

```python
# CÓDIGO ACTUAL - VULNERABLE
@classmethod
def load(cls) -> "GlobalSettings":
    cached = cache.get(GLOBAL_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    
    obj, _ = cls.objects.get_or_create(id=GLOBAL_SETTINGS_SINGLETON_UUID)  # ⚠️ Sin lock
    # ...
```

**Escenario de Fallo**:
1. Request A y B llaman `load()` simultáneamente con caché vacío
2. Ambos ejecutan `get_or_create` sin lock
3. Se crean 2 instancias (una falla por constraint, pero ya hay inconsistencia)

**Solución**:
```python
from django.db import transaction

@classmethod
def load(cls) -> "GlobalSettings":
    cached = cache.get(GLOBAL_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    
    # Usar select_for_update con get_or_create
    with transaction.atomic():
        try:
            obj = cls.objects.select_for_update().get(id=GLOBAL_SETTINGS_SINGLETON_UUID)
        except cls.DoesNotExist:
            obj = cls.objects.create(id=GLOBAL_SETTINGS_SINGLETON_UUID)
        
        if not obj.created_at:
            obj.created_at = timezone.now()
            obj.save(update_fields=["created_at"])
        
        cache.set(GLOBAL_SETTINGS_CACHE_KEY, obj, timeout=None)
        return obj
```

---

### **2. Falta Limpieza Automática de IdempotencyKey**
**Severidad**: CRÍTICA  
**Ubicación**: `models.py` IdempotencyKey, `tasks.py`  
**Código de Error**: `CORE-IDEMPOTENCY-CLEANUP`

**Problema**: Las claves de idempotencia nunca se eliminan, causando crecimiento infinito de la tabla.

**Solución**:
```python
# Nueva tarea en tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task
def cleanup_old_idempotency_keys():
    """
    Elimina claves de idempotencia completadas hace más de 7 días.
    Ejecutar diariamente.
    """
    from .models import IdempotencyKey
    
    cutoff = timezone.now() - timedelta(days=7)
    deleted_count, _ = IdempotencyKey.objects.filter(
        status=IdempotencyKey.Status.COMPLETED,
        completed_at__lt=cutoff
    ).delete()
    
    # También limpiar claves pendientes muy antiguas (posibles fallos)
    stale_cutoff = timezone.now() - timedelta(hours=24)
    stale_count, _ = IdempotencyKey.objects.filter(
        status=IdempotencyKey.Status.PENDING,
        locked_at__lt=stale_cutoff
    ).delete()
    
    return {
        "deleted_completed": deleted_count,
        "deleted_stale": stale_count
    }

# Configurar en Celery Beat
# CELERY_BEAT_SCHEDULE = {
#     'cleanup-idempotency-keys': {
#         'task': 'core.tasks.cleanup_old_idempotency_keys',
#         'schedule': crontab(hour=3, minute=0),  # 3 AM diario
#     },
# }
```

---

### **3. Falta Validación de Unicidad en idempotent_view**
**Severidad**: ALTA  
**Ubicación**: `decorators.py` líneas 11-88  
**Código de Error**: `CORE-IDEMPOTENCY-VALIDATION`

**Problema**: No se valida que el `request_hash` coincida, permitiendo reutilizar la misma clave con diferentes datos.

**Solución**:
```python
import hashlib
import json

def idempotent_view(timeout=60):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(self, request, *args, **kwargs):
            method = getattr(request, "method", "").upper()
            key = request.headers.get("Idempotency-Key")
            if not key:
                return view_func(self, request, *args, **kwargs)
            
            # Calcular hash del request body
            request_hash = ""
            if hasattr(request, 'data') and request.data:
                try:
                    request_hash = hashlib.sha256(
                        json.dumps(request.data, sort_keys=True).encode()
                    ).hexdigest()
                except (TypeError, ValueError):
                    pass
            
            user = request.user if request.user.is_authenticated else None
            
            with transaction.atomic():
                record, created = IdempotencyKey.objects.select_for_update().get_or_create(
                    key=key,
                    defaults={
                        "user": user,
                        "endpoint": request.path,
                        "status": IdempotencyKey.Status.PENDING,
                        "locked_at": timezone.now(),
                        "request_hash": request_hash,  # NUEVO
                    },
                )
                
                if not created:
                    # Validar que el hash coincida
                    if record.request_hash and record.request_hash != request_hash:
                        return Response(
                            {
                                "detail": "La clave de idempotencia ya fue usada con datos diferentes.",
                                "code": "IDEMPOTENCY_KEY_MISMATCH"
                            },
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        )
                    
                    # ... resto del código existente
```

---

### **4. Falta Índice en IdempotencyKey.locked_at**
**Severidad**: ALTA  
**Ubicación**: `models.py` IdempotencyKey.Meta  
**Código de Error**: `CORE-INDEX-MISSING`

**Problema**: La tarea de limpieza filtra por `locked_at` sin índice, causando full table scan.

**Solución**:
```python
# En models.py IdempotencyKey.Meta
class Meta:
    verbose_name = "Idempotency Key"
    verbose_name_plural = "Idempotency Keys"
    ordering = ["-created_at"]
    indexes = [
        models.Index(fields=['key']),  # Ya existe (unique)
        models.Index(fields=['status', 'completed_at']),  # NUEVO - para cleanup
        models.Index(fields=['status', 'locked_at']),     # NUEVO - para cleanup de stale
        models.Index(fields=['user', 'created_at']),      # NUEVO - para queries por usuario
    ]
```

---

### **5. SoftDeleteModel.delete() No Es Atómico**
**Severidad**: ALTA  
**Ubicación**: `models.py` líneas 67-72  
**Código de Error**: `CORE-SOFTDELETE-RACE`

**Problema**: Entre verificar `is_deleted` y guardar, otra transacción podría modificar el objeto.

**Solución**:
```python
from django.db import transaction

def delete(self, using=None, keep_parents=False):
    """Soft delete atómico"""
    if self.is_deleted:
        return
    
    with transaction.atomic():
        # Re-obtener con lock para evitar race condition
        fresh = type(self).objects.select_for_update().get(pk=self.pk)
        if fresh.is_deleted:
            return
        
        fresh.is_deleted = True
        fresh.deleted_at = timezone.now()
        fresh.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
```

---

### **6. Falta Validación de Formato en Logging Filters**
**Severidad**: MEDIA-ALTA  
**Ubicación**: `logging_filters.py` líneas 10-136  
**Código de Error**: `CORE-LOG-SANITIZE`

**Problema**: Los patrones regex pueden fallar con strings malformados, causando excepciones en el logger.

**Solución**:
```python
class SanitizeAPIKeyFilter(logging.Filter):
    def filter(self, record):
        """Sanitiza el mensaje de log antes de que sea emitido."""
        try:
            # Sanitizar el mensaje principal
            if isinstance(record.msg, str):
                for pattern, replacement in self.PATTERNS:
                    try:
                        record.msg = pattern.sub(replacement, record.msg)
                    except Exception:
                        # Si falla un patrón, continuar con los demás
                        continue
            
            # Sanitizar argumentos del mensaje
            if record.args:
                try:
                    if isinstance(record.args, dict):
                        sanitized_args = {}
                        for key, value in record.args.items():
                            if isinstance(value, str):
                                for pattern, replacement in self.PATTERNS:
                                    try:
                                        value = pattern.sub(replacement, value)
                                    except Exception:
                                        continue
                            sanitized_args[key] = value
                        record.args = sanitized_args
                    # ... similar para tuple/list
                except Exception:
                    # Si falla la sanitización de args, dejar args originales
                    pass
        except Exception:
            # En el peor caso, no sanitizar pero permitir que el log se emita
            pass
        
        return True
```

---

### **7. Falta Validación de Roles en Permissions**
**Severidad**: MEDIA  
**Ubicación**: `permissions.py` líneas 30-44  
**Código de Error**: `CORE-PERMISSION-VALIDATION`

**Problema**: `RoleAllowed` no valida que los roles en `required_roles` sean válidos.

**Solución**:
```python
class RoleAllowed(BasePermission):
    """
    Usa en la vista: required_roles = {"CLIENT","VIP","STAFF","ADMIN"}
    """
    message = "Tu rol no está autorizado para esta operación."
    
    VALID_ROLES = {"CLIENT", "VIP", "STAFF", "ADMIN"}
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        required = getattr(view, "required_roles", None)
        if not required:
            return True
        
        # Validar que required_roles contenga roles válidos
        if not isinstance(required, (set, list, tuple)):
            logger.error(
                "required_roles debe ser un set/list/tuple, recibido: %s",
                type(required)
            )
            return False
        
        invalid_roles = set(required) - self.VALID_ROLES
        if invalid_roles:
            logger.error(
                "Roles inválidos en required_roles: %s",
                invalid_roles
            )
            return False
        
        role = getattr(request.user, "role", None)
        return role in required
```

---

### **8. Testing Completamente Ausente**
**Severidad**: CRÍTICA  
**Ubicación**: `tests.py` - archivo vacío  
**Código de Error**: `CORE-NO-TESTS`

**Problema**: El módulo core es crítico y no tiene tests. Cualquier bug afecta a todo el sistema.

**Solución**: Crear suite de tests completa:

```python
# core/tests.py
import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.cache import cache
from unittest.mock import patch

from .models import GlobalSettings, AuditLog, IdempotencyKey, BaseModel, SoftDeleteModel
from .decorators import idempotent_view
from .utils import get_client_ip, safe_audit_log
from users.models import CustomUser

@pytest.mark.django_db
class TestGlobalSettings:
    """Tests para GlobalSettings singleton"""
    
    def test_load_creates_singleton(self):
        """load() debe crear singleton si no existe"""
        cache.clear()
        settings = GlobalSettings.load()
        assert settings.id == GlobalSettings.GLOBAL_SETTINGS_SINGLETON_UUID
    
    def test_load_returns_cached(self):
        """load() debe retornar desde caché si existe"""
        cache.clear()
        settings1 = GlobalSettings.load()
        
        with patch.object(GlobalSettings.objects, 'get_or_create') as mock:
            settings2 = GlobalSettings.load()
            assert settings1.id == settings2.id
            mock.assert_not_called()  # No debe tocar DB
    
    def test_save_invalidates_cache(self):
        """save() debe invalidar caché"""
        cache.clear()
        settings = GlobalSettings.load()
        
        settings.advance_payment_percentage = 25
        settings.save()
        
        cached = cache.get(GlobalSettings.GLOBAL_SETTINGS_CACHE_KEY)
        assert cached.advance_payment_percentage == 25
    
    def test_validation_prevents_invalid_values(self):
        """clean() debe prevenir valores inválidos"""
        settings = GlobalSettings.load()
        settings.advance_payment_percentage = 150  # > 100
        
        with pytest.raises(ValidationError):
            settings.clean()

@pytest.mark.django_db
class TestSoftDeleteModel:
    """Tests para SoftDeleteModel"""
    
    def test_delete_marks_as_deleted(self):
        """delete() debe marcar como eliminado, no borrar"""
        # Crear modelo de prueba que use SoftDeleteModel
        # ... test implementation
        pass
    
    def test_hard_delete_removes_from_db(self):
        """hard_delete() debe eliminar de DB"""
        pass
    
    def test_restore_undeletes(self):
        """restore() debe revertir soft delete"""
        pass

@pytest.mark.django_db
class TestIdempotencyKey:
    """Tests para IdempotencyKey"""
    
    def test_idempotent_view_prevents_duplicate_requests(self):
        """Decorator debe prevenir requests duplicados"""
        pass
    
    def test_idempotent_view_allows_retry_after_timeout(self):
        """Decorator debe permitir retry después de timeout"""
        pass

@pytest.mark.django_db
class TestAuditLog:
    """Tests para AuditLog"""
    
    def test_audit_log_creation(self, admin_user, client_user):
        """Debe crear log de auditoría correctamente"""
        log = AuditLog.objects.create(
            action=AuditLog.Action.FLAG_NON_GRATA,
            admin_user=admin_user,
            target_user=client_user,
            details="Test details"
        )
        
        assert log.action == AuditLog.Action.FLAG_NON_GRATA
        assert log.admin_user == admin_user
        assert log.target_user == client_user

# ... más tests
```

**Prioridad**: Implementar al menos tests de GlobalSettings y IdempotencyKey antes de producción.

---

## 🟡 IMPORTANTES (14) - Primera Iteración Post-Producción

### **9. Falta Logging en Operaciones Críticas de GlobalSettings**
**Severidad**: MEDIA  
**Ubicación**: `models.py` GlobalSettings.save()  

**Solución**:
```python
import logging
logger = logging.getLogger(__name__)

def save(self, *args, **kwargs):
    self.pk = self.id = GLOBAL_SETTINGS_SINGLETON_UUID
    
    # Log cambios importantes
    if self.pk:
        try:
            old = GlobalSettings.objects.get(pk=self.pk)
            changes = []
            for field in ['advance_payment_percentage', 'low_supervision_capacity', 
                         'developer_commission_percentage']:
                old_val = getattr(old, field)
                new_val = getattr(self, field)
                if old_val != new_val:
                    changes.append(f"{field}: {old_val} -> {new_val}")
            
            if changes:
                logger.warning(
                    "GlobalSettings modificado: %s",
                    ", ".join(changes)
                )
        except GlobalSettings.DoesNotExist:
            pass
    
    self.full_clean()
    super().save(*args, **kwargs)
    cache.set(GLOBAL_SETTINGS_CACHE_KEY, self, timeout=None)
```

---

### **10. Falta Validación de Longitud en IdempotencyKey.key**
**Severidad**: MEDIA  
**Ubicación**: `models.py` IdempotencyKey  

**Solución**:
```python
# En models.py IdempotencyKey
from django.core.validators import MinLengthValidator

key = models.CharField(
    max_length=255,
    unique=True,
    validators=[MinLengthValidator(16)]  # NUEVO - mínimo 16 caracteres
)
```

---

### **11. Falta Rate Limiting Específico para Endpoints Admin**
**Severidad**: MEDIA  
**Ubicación**: `throttling.py`  

**Solución**:
```python
# En throttling.py
class AdminThrottle(UserRateThrottle):
    scope = "admin"  # '1000/hour' en settings
    
    def allow_request(self, request, view):
        # Solo aplicar a usuarios admin
        if not request.user or not request.user.is_authenticated:
            return True
        
        if getattr(request.user, 'role', '') != 'ADMIN':
            return True
        
        return super().allow_request(request, view)
```

---

### **12. Falta Sanitización de Números de Tarjeta en Logs**
**Severidad**: ALTA  
**Ubicación**: `logging_filters.py` SanitizePIIFilter  

**Solución**:
```python
# Agregar a SanitizePIIFilter.PATTERNS
# Números de tarjeta de crédito
(
    re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),
    '****-****-****-****'
),
```

---

### **13. Falta Validación de Timezone en GlobalSettings**
**Severidad**: MEDIA  
**Ubicación**: `models.py` GlobalSettings.clean()  

**Solución**:
```python
from zoneinfo import ZoneInfo, available_timezones

def clean(self):
    errors = {}
    # ... validaciones existentes ...
    
    # Validar timezone
    if self.timezone_display:
        try:
            ZoneInfo(self.timezone_display)
        except Exception:
            errors["timezone_display"] = f"Timezone inválido: {self.timezone_display}"
    
    if errors:
        raise ValidationError(errors)
```

---

### **14. Falta Método para Obtener Settings Específicos**
**Severidad**: BAJA-MEDIA  
**Ubicación**: `services.py`  

**Solución**:
```python
# En services.py
def get_setting(key: str, default=None):
    """
    Obtiene un setting específico sin cargar todo el objeto.
    Útil para optimizar queries.
    """
    try:
        settings = GlobalSettings.load()
        return getattr(settings, key, default)
    except Exception:
        return default
```

---

### **15. Falta Documentación de Patrones de Uso**
**Severidad**: MEDIA  
**Ubicación**: Todos los archivos  

**Solución**: Crear `core/README.md`:

```markdown
# Core Module Documentation

## BaseModel
Modelo base abstracto que proporciona:
- `id`: UUID primary key
- `created_at`: Timestamp de creación
- `updated_at`: Timestamp de última modificación

**Uso**:
```python
from core.models import BaseModel

class MyModel(BaseModel):
    name = models.CharField(max_length=100)
```

## SoftDeleteModel
Extiende BaseModel con soft delete:
- `is_deleted`: Boolean flag
- `deleted_at`: Timestamp de eliminación

**Managers**:
- `objects`: Solo objetos no eliminados
- `all_objects`: Todos los objetos

**Métodos**:
- `delete()`: Soft delete
- `hard_delete()`: Eliminación permanente
- `restore()`: Restaurar objeto eliminado

## GlobalSettings
Singleton para configuración global del sistema.

**Uso**:
```python
from core.models import GlobalSettings

settings = GlobalSettings.load()  # Siempre usa load(), no get()
advance_percentage = settings.advance_payment_percentage
```

## Idempotency
Decorator para prevenir requests duplicados.

**Uso**:
```python
from core.decorators import idempotent_view

class MyViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    @idempotent_view(timeout=60)
    def create_order(self, request):
        # Cliente debe enviar header: Idempotency-Key: <uuid>
        pass
```

## Permissions
- `IsAdmin`: Solo usuarios con role=ADMIN
- `IsStaff`: Usuarios con role=STAFF o ADMIN
- `RoleAllowed`: Flexible, define `required_roles` en la vista

## Data Masking
Serializer mixin para enmascarar datos sensibles por rol.

**Uso**:
```python
from core.serializers import DataMaskingMixin

class UserSerializer(DataMaskingMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number']
        mask_fields = {
            "phone_number": {"mask_with": "phone", "visible_for": ["STAFF"]},
            "email": {"mask_with": "email", "visible_for": ["STAFF"]},
        }
```
```

---

### **16-22**: Mejoras adicionales de documentación, logging, validaciones, índices, etc.

---

## 🟢 MEJORAS (8) - Implementar Según Necesidad

### **23. Agregar Versionado a GlobalSettings**
**Severidad**: BAJA  

**Solución**:
```python
# En models.py GlobalSettings
version = models.PositiveIntegerField(default=1)

def save(self, *args, **kwargs):
    if self.pk:
        self.version += 1
    # ... resto del código
```

---

### **24. Implementar Circuit Breaker para Cache**
**Severidad**: BAJA  

**Solución**:
```python
# En utils.py
from functools import wraps
import time

class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.timeout:
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = 'OPEN'
            raise e

cache_circuit_breaker = CircuitBreaker()
```

---

### **25-30**: Más mejoras opcionales (métricas, dashboards, etc.)

---

## 📊 RESUMEN DE PRIORIDADES

### 🔴 CRÍTICAS (8) - Implementar ANTES de Producción
1. **#1** - Race condition en GlobalSettings.load()
2. **#2** - Falta limpieza automática de IdempotencyKey
3. **#3** - Falta validación de unicidad en idempotent_view
4. **#4** - Falta índice en IdempotencyKey.locked_at
5. **#5** - SoftDeleteModel.delete() no es atómico
6. **#6** - Falta validación de formato en logging filters
7. **#7** - Falta validación de roles en permissions
8. **#8** - Testing completamente ausente

### 🟡 IMPORTANTES (14) - Primera Iteración Post-Producción
9-22: Logging, validaciones, documentación, índices adicionales

### 🟢 MEJORAS (8) - Implementar Según Necesidad
23-30: Versionado, circuit breakers, métricas avanzadas

---

## 💡 RECOMENDACIONES ADICIONALES

### Monitoreo en Producción
- Alertas para cambios en GlobalSettings
- Monitoreo de crecimiento de IdempotencyKey
- Métricas de uso de caché

### Documentación
- Crear guía de uso de cada componente
- Documentar patrones de diseño
- Crear ejemplos de uso

### Seguridad
- Auditar todos los filtros de sanitización
- Validar permisos en todos los endpoints
- Implementar rate limiting granular

---

**Próximos Pasos Recomendados**:
1. Implementar las 8 mejoras críticas
2. Crear suite de tests (mínimo 60% cobertura)
3. Documentar componentes principales
4. Configurar monitoreo y alertas
5. Realizar code review de seguridad
