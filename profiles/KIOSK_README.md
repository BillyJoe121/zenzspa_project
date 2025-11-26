# 🖥️ Sistema de Kiosko - ZenzSpa

## Descripción

El sistema de kiosko permite que dispositivos dedicados (tablets, pantallas táctiles) funcionen en modo restringido para que los clientes puedan:
- Completar cuestionarios de Dosha
- Actualizar su perfil clínico
- Ver información limitada

El middleware `KioskFlowEnforcementMiddleware` restringe el acceso a solo las rutas permitidas.

---

## 🔧 Configuración de Variables de Entorno

### Variables Requeridas

```bash
# Tiempo de inactividad antes de cerrar sesión automáticamente (en minutos)
KIOSK_SESSION_TIMEOUT_MINUTES=10

# URL de la pantalla segura a la que redirigir después del timeout
KIOSK_SECURE_SCREEN_URL=/kiosk/secure

# Prefijos de rutas permitidas (separados por espacios)
KIOSK_ALLOWED_PATH_PREFIXES="/api/v1/kiosk/ /api/v1/users/ /api/v1/dosha-quiz/"

# Nombres de vistas permitidas (separados por espacios)
KIOSK_ALLOWED_VIEW_NAMES="clinical-profile-me clinical-profile-list clinical-profile-detail clinical-profile-update"
```

### Ejemplo de `.env`

```bash
# Configuración de Kiosko
KIOSK_SESSION_TIMEOUT_MINUTES=10
KIOSK_SECURE_SCREEN_URL=/kiosk/secure
KIOSK_ALLOWED_PATH_PREFIXES="/api/v1/kiosk/ /api/v1/users/ /api/v1/dosha-quiz/ /api/v1/profiles/"
KIOSK_ALLOWED_VIEW_NAMES="clinical-profile-me clinical-profile-list clinical-profile-detail clinical-profile-update dosha-quiz-start dosha-quiz-submit"
```

---

## 🚀 Flujo de Uso

### 1. Activar Modo Kiosko

El frontend debe establecer una sesión de kiosko llamando al endpoint:

```http
POST /api/v1/kiosk/activate/
Content-Type: application/json

{
  "device_id": "KIOSK-001",
  "location": "Recepción Principal"
}
```

Respuesta:
```json
{
  "status": "activated",
  "session_id": "kiosk_abc123",
  "timeout_minutes": 10
}
```

### 2. Rutas Permitidas

Una vez activado el modo kiosko, solo se pueden acceder a:

- `/api/v1/kiosk/*` - Endpoints específicos de kiosko
- `/api/v1/users/` - Información básica de usuario
- `/api/v1/dosha-quiz/` - Cuestionario de Dosha
- `/api/v1/profiles/clinical-profile/` - Perfil clínico (solo lectura/actualización)

### 3. Timeout Automático

Después de `KIOSK_SESSION_TIMEOUT_MINUTES` minutos de inactividad:
- La sesión se cierra automáticamente
- El usuario es redirigido a `KIOSK_SECURE_SCREEN_URL`
- Se ejecuta la tarea `cleanup_expired_kiosk_sessions` (Celery)

### 4. Desactivar Modo Kiosko

```http
POST /api/v1/kiosk/deactivate/
```

---

## 🔒 Seguridad

### Restricciones Implementadas

1. **Rutas Bloqueadas**: Cualquier ruta no incluida en `KIOSK_ALLOWED_PATH_PREFIXES` será bloqueada
2. **Vistas Bloqueadas**: Solo las vistas en `KIOSK_ALLOWED_VIEW_NAMES` son accesibles
3. **Timeout Automático**: Sesiones inactivas se cierran automáticamente
4. **Sin Acceso Admin**: El panel de administración está completamente bloqueado
5. **Sin Pagos**: Los endpoints de pagos están bloqueados por defecto

### Auditoría

Todas las acciones en modo kiosko son registradas por:
- `AdminAuditMiddleware` - Registra cambios administrativos
- `HistoryRequestMiddleware` (django-simple-history) - Historial de cambios

---

## 🧪 Testing

### Probar Activación de Kiosko

```bash
# Activar modo kiosko
curl -X POST http://localhost:8000/api/v1/kiosk/activate/ \
  -H "Content-Type: application/json" \
  -d '{"device_id": "TEST-001", "location": "Testing"}'

# Intentar acceder a ruta permitida
curl http://localhost:8000/api/v1/kiosk/status/

# Intentar acceder a ruta bloqueada (debe fallar)
curl http://localhost:8000/api/v1/finances/payouts/
```

### Verificar Timeout

```python
# En Django shell
from profiles.models import KioskSession
from django.utils import timezone
from datetime import timedelta

# Crear sesión expirada
session = KioskSession.objects.create(
    device_id="TEST-001",
    last_activity=timezone.now() - timedelta(minutes=15)
)

# Ejecutar limpieza
from profiles.tasks import cleanup_expired_kiosk_sessions
cleanup_expired_kiosk_sessions()

# Verificar que la sesión fue eliminada
print(KioskSession.objects.filter(device_id="TEST-001").exists())  # False
```

---

## 📊 Monitoreo

### Métricas Importantes

1. **Sesiones Activas**: Número de dispositivos kiosko activos
2. **Timeouts por Día**: Cuántas sesiones expiran automáticamente
3. **Intentos de Acceso Bloqueados**: Intentos de acceder a rutas no permitidas

### Logs

Los logs de kiosko se encuentran en:
```
logs/zenzspa.log
```

Buscar por:
```bash
grep "kiosk" logs/zenzspa.log
grep "KioskFlowEnforcementMiddleware" logs/zenzspa.log
```

---

## 🛠️ Troubleshooting

### Problema: Sesión de Kiosko No Se Activa

**Solución**:
1. Verificar que las variables de entorno están configuradas
2. Revisar logs: `grep "kiosk" logs/zenzspa.log`
3. Verificar que el middleware está habilitado en `settings.py`

### Problema: Rutas Permitidas No Funcionan

**Solución**:
1. Verificar `KIOSK_ALLOWED_PATH_PREFIXES` en `.env`
2. Asegurarse de que los prefijos terminan con `/`
3. Revisar que las vistas tienen los nombres correctos en `KIOSK_ALLOWED_VIEW_NAMES`

### Problema: Timeout No Funciona

**Solución**:
1. Verificar que Celery está corriendo: `celery -A zenzspa inspect ping`
2. Verificar que la tarea está programada: `celery -A zenzspa inspect scheduled`
3. Revisar logs de Celery: `celery -A zenzspa worker --loglevel=info`

---

## 📝 Notas de Producción

1. **Dispositivos Físicos**: Configurar tablets en modo kiosko del sistema operativo
2. **Red Dedicada**: Considerar VLAN separada para dispositivos kiosko
3. **Backups**: Las sesiones de kiosko se limpian automáticamente, no requieren backup
4. **Actualizaciones**: Reiniciar dispositivos kiosko después de deploys importantes

---

## 🔗 Referencias

- Middleware: `profiles/middleware.py` - `KioskFlowEnforcementMiddleware`
- Modelos: `profiles/models.py` - `KioskSession`
- Tareas: `profiles/tasks.py` - `cleanup_expired_kiosk_sessions`
- Configuración: `zenzspa/settings.py` - Variables `KIOSK_*`
