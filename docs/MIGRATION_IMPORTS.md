# Guía de Migración de Imports - Core Modules

## Resumen

Durante el refactor, los siguientes módulos fueron reorganizados:

| Import Antiguo (DEPRECADO) | Import Nuevo (RECOMENDADO) |
|---------------------------|---------------------------|
| `from core.exceptions import ...` | `from core.utils.exceptions import ...` |
| `from core.metrics import ...` | `from core.infra.metrics import ...` |
| `from core.caching import ...` | `from core.utils.caching import ...` |

## Estado Actual

✅ **Compatibilidad hacia atrás IMPLEMENTADA**

Se han creado archivos de compatibilidad (`core/exceptions.py`, `core/metrics.py`, `core/caching.py`) que redirigen automáticamente a las nuevas ubicaciones. Esto significa que:

1. **El código antiguo sigue funcionando** sin modificaciones
2. **Se emiten warnings de deprecación** para facilitar la migración
3. **Los imports antiguos y nuevos referencian exactamente los mismos objetos**

## Ejemplos de Migración

### BusinessLogicError

**Antes (deprecado pero funcional):**
```python
from core.exceptions import BusinessLogicError
```

**Después (recomendado):**
```python
from core.utils.exceptions import BusinessLogicError
```

### Métricas

**Antes (deprecado pero funcional):**
```python
from core.metrics import get_histogram, get_counter
```

**Después (recomendado):**
```python
from core.infra.metrics import get_histogram, get_counter
```

### Caching

**Antes (deprecado pero funcional):**
```python
from core.caching import acquire_lock
```

**Después (recomendado):**
```python
from core.utils.caching import acquire_lock
```

## Verificación del Código

### Apps que ya usan los nuevos imports

Las siguientes apps **YA están actualizadas** al nuevo sistema:

- ✅ `spa/` - Completamente migrado
- ✅ `spa/models/`
- ✅ `spa/services/`
- ✅ `spa/views/`
- ✅ `spa/tests/`

### Apps verificadas sin imports deprecados

Se verificaron todas las apps activas y **NINGUNA** usa los imports antiguos:

- ✅ `analytics/`
- ✅ `blog/`
- ✅ `bot/`
- ✅ `finances/`
- ✅ `legal/`
- ✅ `marketplace/`
- ✅ `monitoring/`
- ✅ `notifications/`
- ✅ `profiles/`
- ✅ `promociones/`
- ✅ `users/`

### Código con imports antiguos (ignorar)

Los únicos archivos con imports antiguos están en:
- `OLDspa/` - Código deprecado que será eliminado
- `*.bak` - Archivos de respaldo

## Plan de Deprecación

### Fase 1: Compatibilidad (ACTUAL) ✅
- Los imports antiguos funcionan con warnings de deprecación
- Archivos de compatibilidad en: `core/exceptions.py`, `core/metrics.py`, `core/caching.py`

### Fase 2: Migración Gradual (Próximos 3-6 meses)
- Actualizar cualquier código nuevo para usar las rutas nuevas
- Revisar logs para identificar warnings de deprecación
- Migrar código existente gradualmente

### Fase 3: Eliminación (Futuro)
- Después de 6 meses sin warnings de deprecación en producción
- Eliminar archivos de compatibilidad: `core/exceptions.py`, `core/metrics.py`, `core/caching.py`
- Los imports antiguos dejarán de funcionar

## Cómo Detectar Código que Necesita Migración

### En desarrollo local:

Los warnings de deprecación aparecerán en la consola cuando uses los imports antiguos:

```
DeprecationWarning: Importing from 'core.exceptions' is deprecated.
Use 'core.utils.exceptions' instead.
```

### Buscar en el código:

```bash
# Buscar todos los imports antiguos
grep -r "from core.exceptions import" --include="*.py" .
grep -r "from core.metrics import" --include="*.py" .
grep -r "from core.caching import" --include="*.py" .
```

### Reemplazar automáticamente:

```bash
# Reemplazar en todos los archivos Python (¡HACER BACKUP PRIMERO!)
find . -name "*.py" -type f -exec sed -i 's/from core\.exceptions import/from core.utils.exceptions import/g' {} +
find . -name "*.py" -type f -exec sed -i 's/from core\.metrics import/from core.infra.metrics import/g' {} +
find . -name "*.py" -type f -exec sed -i 's/from core\.caching import/from core.utils.caching import/g' {} +
```

## Testing

Se ha verificado que:

1. ✅ Los imports antiguos funcionan correctamente
2. ✅ Los imports nuevos funcionan correctamente
3. ✅ Ambos imports referencian exactamente los mismos objetos
4. ✅ Se emiten warnings de deprecación apropiados
5. ✅ No hay código activo usando los imports antiguos

## Archivos Creados

Los siguientes archivos de compatibilidad fueron creados:

- `core/exceptions.py` - Redirige a `core.utils.exceptions`
- `core/metrics.py` - Redirige a `core.infra.metrics`
- `core/caching.py` - Redirige a `core.utils.caching`

## Próximos Pasos

1. **Corto plazo (Opcional):**
   - Continuar usando el código como está
   - Los imports antiguos seguirán funcionando

2. **Mediano plazo (Recomendado):**
   - Actualizar código nuevo para usar rutas nuevas
   - Migrar gradualmente código existente cuando se hagan modificaciones

3. **Largo plazo:**
   - Después de 6 meses, eliminar archivos de compatibilidad
   - Todos los imports deberán usar las nuevas rutas

---

**Fecha de creación:** 2026-01-10
**Versión:** 1.0
**Estado:** Compatibilidad hacia atrás implementada y verificada
