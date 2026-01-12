# 🔐 Guía de Seguridad - StudioZens

## Índice
1. [Django Axes - Protección contra Fuerza Bruta](#django-axes)
2. [Rate Limiting](#rate-limiting)
3. [Validación de Variables de Entorno](#validación-de-variables)
4. [Headers de Seguridad](#headers-de-seguridad)
5. [Configuración de Cookies](#cookies)
6. [Content Security Policy (CSP)](#csp)
7. [Monitoreo y Alertas](#monitoreo)

---

## Django Axes - Protección contra Fuerza Bruta {#django-axes}

### ¿Qué es Django Axes?

Django Axes es un sistema de detección y bloqueo de intentos de login por fuerza bruta. Monitorea intentos fallidos de autenticación y bloquea temporalmente IPs o usuarios sospechosos.

### ¿Cuándo Activarlo?

**Activar en producción si:**
- Usas el panel de administración de Django (`/admin/`)
- Tienes endpoints de login con usuario/contraseña (además de OTP)
- Has detectado intentos de fuerza bruta en los logs

**NO activar si:**
- Solo usas autenticación OTP/SMS (Twilio Verify)
- No tienes login tradicional con contraseña
- El rate limiting de DRF es suficiente

### Configuración

#### 1. Activar Django Axes

En tu archivo `.env`:

```bash
# Activar django-axes
AXES_ENABLED=1

# Número de intentos fallidos antes de bloquear (default: 5)
AXES_FAILURE_LIMIT=5

# Tiempo de bloqueo en minutos (default: 10)
AXES_COOLOFF_TIME_MIN=10
```

#### 2. Variables Disponibles

| Variable | Default | Descripción |
|----------|---------|-------------|
| `AXES_ENABLED` | `0` | Activar/desactivar Axes |
| `AXES_FAILURE_LIMIT` | `5` | Intentos fallidos antes de bloquear |
| `AXES_COOLOFF_TIME_MIN` | `10` | Minutos de bloqueo |

### Configuración Actual en `settings.py`

```python
AXES_ENABLED = os.getenv("AXES_ENABLED", "0") in ("1", "true", "True")
if AXES_ENABLED:
    AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
    AXES_COOLOFF_TIME = int(os.getenv("AXES_COOLOFF_TIME_MIN", "10"))
    AXES_ONLY_USER_FAILURES = False
    AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True
```

**Configuración explicada:**
- `AXES_ONLY_USER_FAILURES = False`: Bloquea por IP también, no solo por usuario
- `AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True`: Bloquea la combinación usuario+IP específica

### Monitoreo de Ataques

#### Integración con Sentry

Para enviar alertas de bloqueos a Sentry, agrega este código en `users/signals.py`:

```python
from axes.signals import user_locked_out
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

@receiver(user_locked_out)
def log_user_locked_out(sender, request, username, **kwargs):
    """Enviar alerta a Sentry cuando un usuario es bloqueado por Axes"""
    ip_address = request.META.get('REMOTE_ADDR', 'unknown')
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    
    logger.warning(
        f"Usuario bloqueado por intentos de fuerza bruta: {username} desde IP {ip_address}",
        extra={
            'username': username,
            'ip_address': ip_address,
            'user_agent': user_agent,
        }
    )
```

#### Métricas a Monitorear

1. **Bloqueos por Día**: Número de IPs/usuarios bloqueados
2. **IPs Más Bloqueadas**: Identificar ataques coordinados
3. **Horarios de Ataques**: Detectar patrones

#### Consultas Útiles

```python
# En Django shell
from axes.models import AccessAttempt, AccessLog

# Ver intentos fallidos recientes
AccessAttempt.objects.filter(
    failures_since_start__gte=3
).order_by('-attempt_time')[:10]

# Ver IPs bloqueadas actualmente
from django.utils import timezone
from datetime import timedelta

recent = timezone.now() - timedelta(minutes=10)
AccessAttempt.objects.filter(
    attempt_time__gte=recent,
    failures_since_start__gte=5
).values('ip_address').distinct()
```

### Comandos de Gestión

```bash
# Ver intentos de acceso
python manage.py axes_list_attempts

# Desbloquear un usuario específico
python manage.py axes_reset_username <username>

# Desbloquear una IP específica
python manage.py axes_reset_ip <ip_address>

# Limpiar todos los bloqueos
python manage.py axes_reset
```

### Logs

Los eventos de Axes se registran en:
```
logs/studiozens.log
logs/errors.log
```

Buscar eventos:
```bash
# Ver bloqueos
grep "locked out" logs/studiozens.log

# Ver intentos fallidos
grep "AXES" logs/studiozens.log
```

---

## Rate Limiting {#rate-limiting}

### Configuración Actual

StudioZens usa el sistema de throttling de Django REST Framework con scopes específicos:

| Scope | Límite Default | Uso |
|-------|----------------|-----|
| `user` | 100/min | Usuarios autenticados (general) |
| `anon` | 30/min | Usuarios anónimos (general) |
| `auth_login` | 3/min | Endpoint de login |
| `auth_verify` | 3/10min | Verificación OTP |
| `payments` | 30/min | Endpoints de pagos |
| `bot` | 5/min | Interacciones con bot |
| `bot_daily` | 100/day | Límite diario del bot |
| `bot_ip` | 20/hour | Bot por IP |
| `admin` | 1000/hour | Panel administrativo |
| `appointments_create` | 10/hour | Crear citas |
| `profile_update` | 20/hour | Actualizar perfil |
| `analytics_export` | 5/hour | Exportar analytics |

### Personalizar Límites

En tu archivo `.env`:

```bash
# Rate limiting personalizado
THROTTLE_USER=200/min
THROTTLE_ANON=50/min
THROTTLE_AUTH_LOGIN=5/min
THROTTLE_PAYMENTS=50/min
```

### Aplicar Throttling a una Vista

```python
from rest_framework.decorators import throttle_classes
from rest_framework.throttling import ScopedRateThrottle

class PaymentView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'payments'
    
    def post(self, request):
        # Limitado a 30/min por default
        pass
```

---

## Validación de Variables de Entorno {#validación-de-variables}

### Variables Validadas al Inicio

StudioZens valida automáticamente variables críticas en `settings.py`:

**Siempre requeridas:**
- `SECRET_KEY`
- `DB_PASSWORD`

**Requeridas en producción (DEBUG=False):**
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_VERIFY_SERVICE_SID`
- `WOMPI_PUBLIC_KEY`
- `WOMPI_INTEGRITY_SECRET`
- `WOMPI_EVENT_SECRET`
- `GEMINI_API_KEY`
- `REDIS_URL` (debe usar `rediss://` con TLS)
- `CELERY_BROKER_URL` (debe usar `rediss://` con TLS)
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `ALLOWED_HOSTS` (sin localhost)
- `CORS_ALLOWED_ORIGINS` (sin localhost)
- `CSRF_TRUSTED_ORIGINS`
- `SITE_URL` (debe usar `https://`)
- `DEFAULT_FROM_EMAIL`
- `WOMPI_REDIRECT_URL` (debe usar `https://`)

### Script de Validación

Ejecutar antes de deploy:

```bash
python -m scripts.validate_settings
```

Este script verifica:
1. Todas las variables requeridas están presentes
2. Los valores son válidos (URLs con HTTPS, etc.)
3. No hay configuraciones inseguras en producción

---

## Headers de Seguridad {#headers-de-seguridad}

### Headers Configurados Automáticamente

En producción (`DEBUG=False`), se activan automáticamente:

```python
# SSL/TLS
SECURE_SSL_REDIRECT = True  # Redirigir HTTP → HTTPS
SECURE_HSTS_SECONDS = 31536000  # 1 año
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Protección XSS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Clickjacking
X_FRAME_OPTIONS = "DENY"
```

### Configuración para Balanceadores/Proxies

Si usas NGINX, ALB, Cloudflare, etc., activa:

```bash
# En .env
TRUST_PROXY=1
```

Esto habilita:
```python
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

**IMPORTANTE**: Solo activar si confías en el proxy. Configurar mal puede causar vulnerabilidades.

---

## Configuración de Cookies {#cookies}

### Cookies de Sesión

```python
SESSION_COOKIE_SECURE = True  # Solo HTTPS (en producción)
SESSION_COOKIE_HTTPONLY = True  # No accesible desde JavaScript
SESSION_COOKIE_SAMESITE = "Lax"  # Protección CSRF
```

### Cookies CSRF

```python
CSRF_COOKIE_SECURE = True  # Solo HTTPS (en producción)
CSRF_COOKIE_HTTPONLY = False  # Debe ser False para que JS pueda leerla
CSRF_COOKIE_SAMESITE = "None" if CORS_ALLOW_CREDENTIALS else "Lax"
```

**Nota**: Si tu frontend está en un dominio diferente y necesita enviar cookies, usa:
```bash
CORS_ALLOW_CREDENTIALS=1
SESSION_COOKIE_SAMESITE=None
```

---

## Content Security Policy (CSP) {#csp}

### Configuración Actual

```python
CSP_DIRECTIVES = {
    "default-src": ("'self'",),
    "script-src": ("'self'", "cdn.jsdelivr.net", "unpkg.com"),
    "style-src": ("'self'", "fonts.googleapis.com", "cdn.jsdelivr.net"),
    "img-src": ("'self'", "data:", "blob:", "https://production.wompi.co"),
    "font-src": ("'self'", "fonts.gstatic.com", "cdn.jsdelivr.net"),
    "connect-src": ("'self'", "wss:", "https://api.twilio.com", 
                    "https://production.wompi.co", ...CORS_ALLOWED_ORIGINS),
}
```

### Habilitar Reportes CSP

```bash
# En .env
CSP_REPORT_URI=https://tu-dominio.com/api/csp-report/
```

Esto enviará reportes de violaciones CSP para monitoreo.

---

## Monitoreo y Alertas {#monitoreo}

### Sentry

Configurado automáticamente si defines:

```bash
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENV=production
SENTRY_TRACES_SAMPLE_RATE=0.1
GIT_COMMIT=abc123  # Para tracking de releases
```

**Integraciones activas:**
- Django
- Celery
- Release tracking

### New Relic

Configurar archivo `newrelic.ini` y definir:

```bash
NEW_RELIC_LICENSE_KEY=...
NEW_RELIC_CONFIG_FILE=/path/to/newrelic.ini
NEW_RELIC_ENV=production
```

### Métricas de Performance

El middleware `PerformanceLoggingMiddleware` registra requests lentas:

```bash
# En .env
SLOW_REQUEST_THRESHOLD=1.0  # segundos
```

Buscar en logs:
```bash
grep "Slow request" logs/studiozens.log
```

---

## Checklist de Seguridad Pre-Producción

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` único y seguro
- [ ] `ALLOWED_HOSTS` configurado correctamente
- [ ] `CORS_ALLOWED_ORIGINS` sin localhost
- [ ] `REDIS_URL` usa `rediss://` (TLS)
- [ ] `CELERY_BROKER_URL` usa `rediss://` (TLS)
- [ ] `SITE_URL` usa `https://`
- [ ] `WOMPI_REDIRECT_URL` usa `https://`
- [ ] Sentry configurado
- [ ] Backups automáticos funcionando
- [ ] Health check responde correctamente
- [ ] Rate limiting probado
- [ ] Django Axes activado (si aplica)
- [ ] Logs rotando correctamente
- [ ] Variables de entorno validadas: `python -m scripts.validate_settings`

---

## Referencias

- **Settings**: `studiozens/settings.py`
- **Middleware**: `core/middleware.py`
- **Health Check**: `studiozens/health.py`
- **Validación**: `scripts/validate_settings.py`
- **Backups**: `scripts/backup_db.sh`
