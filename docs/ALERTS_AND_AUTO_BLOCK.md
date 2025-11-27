# Sistema de Alertas y Auto-Bloqueo

## 📧 Alertas por Email para Actividades Críticas

### ¿Qué son las Alertas Críticas?

El sistema envía automáticamente emails a los administradores cuando se detecta una **actividad sospechosa CRÍTICA**, como:

- 🚨 **Intentos de Jailbreak**: Usuario intentando manipular el prompt del sistema
- 🚨 **Contenido Malicioso**: Contenido peligroso o inapropiado detectado por Gemini

### Configuración de Alertas

#### 1. En el Admin de Django

1. Ve a: **Admin → Bot → Configuración del Bot**
2. Sección: **"Alertas de Seguridad"**
3. Configuración disponible:
   - ✅ **Habilitar Alertas Críticas**: Activa/desactiva el envío de emails

#### 2. Configurar Emails de Administradores

Las alertas se envían a todos los usuarios con rol **ADMIN** o **SUPERUSER** que tengan un email configurado.

**Opción A: Desde el Admin de Django**
```
Admin → Users → Usuarios
- Buscar usuarios con rol ADMIN
- Verificar que tengan email configurado
```

**Opción B: En settings.py** (alternativo)
```python
# En studiozens/settings.py
ADMINS = [
    ('Admin Name', 'admin@example.com'),
    ('Another Admin', 'admin2@example.com'),
]

# Email settings (requerido para enviar emails)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'noreply@studiozens.com'
```

### Ejemplo de Email de Alerta

```
Subject: [ALERTA CRÍTICA] Intento de Jailbreak - 192.168.1.100

⚠️ ALERTA DE SEGURIDAD - ACTIVIDAD CRÍTICA DETECTADA ⚠️

Tipo: Intento de Jailbreak
Severidad: Crítica
Usuario/IP: Visitante abc123
IP: 192.168.1.100
Fecha: 2025-01-24 15:30:45

DESCRIPCIÓN:
Intento de jailbreak o manipulación del prompt del sistema

ACCIÓN REQUERIDA:
Por favor, revisa esta actividad inmediatamente en el panel de administración:
https://tudominio.com/admin/bot/suspiciousactivity/123/change/

Considera bloquear esta IP si el patrón de abuso continúa.

---
Este es un mensaje automático del sistema de seguridad de Studiozens Bot.
```

---

## 🚫 Auto-Bloqueo de IPs Maliciosas

### ¿Qué es el Auto-Bloqueo?

El sistema puede **bloquear automáticamente** una IP cuando detecta múltiples actividades críticas en un período de tiempo.

**Ventajas:**
- ✅ Respuesta inmediata a amenazas
- ✅ Protección 24/7 sin intervención manual
- ✅ Previene abuso continuo

### Configuración de Auto-Bloqueo

#### En el Admin de Django

1. Ve a: **Admin → Bot → Configuración del Bot**
2. Sección: **"Auto-Bloqueo"**
3. Configuración disponible:

| Campo | Descripción | Valor por Defecto |
|-------|-------------|-------------------|
| **Habilitar Auto-Bloqueo** | Activa/desactiva la funcionalidad | ✅ Habilitado |
| **Umbral de Actividades Críticas** | Número de actividades críticas antes de bloquear | 3 |
| **Período de Análisis (horas)** | Ventana de tiempo para contar actividades | 24 horas |

#### Ejemplo de Configuración

**Configuración Estricta** (para alta seguridad):
- Umbral: **2 actividades críticas**
- Período: **12 horas**
- Resultado: Bloquea después de 2 actividades críticas en 12 horas

**Configuración Moderada** (recomendada):
- Umbral: **3 actividades críticas**
- Período: **24 horas**
- Resultado: Bloquea después de 3 actividades críticas en 1 día

**Configuración Permisiva**:
- Umbral: **5 actividades críticas**
- Período: **48 horas**
- Resultado: Bloquea después de 5 actividades críticas en 2 días

### ¿Cómo Funciona el Auto-Bloqueo?

1. **Usuario comete actividad crítica** (ej: intento de jailbreak)
2. **Sistema registra la actividad** en la base de datos
3. **Sistema cuenta actividades críticas** de esa IP en el período configurado
4. **Si alcanza el umbral:**
   - ✅ IP se bloquea automáticamente
   - ✅ Se envía notificación por email a los admins
   - ✅ Se registra en "IPs Bloqueadas"
5. **Usuario bloqueado ve:**
   ```
   "Tu IP ha sido bloqueada por: Abuso de Límites.
    Contacta al administrador si crees que esto es un error."
   ```

### Email de Auto-Bloqueo

Cuando una IP es bloqueada automáticamente, los admins reciben:

```
Subject: [AUTO-BLOQUEO] IP 192.168.1.100 bloqueada automáticamente

🚫 BLOQUEO AUTOMÁTICO DE IP 🚫

La IP 192.168.1.100 ha sido bloqueada automáticamente por el sistema de seguridad.

Razón: Múltiples actividades críticas detectadas
Actividades críticas detectadas: 3
Fecha: 2025-01-24 16:45:30

Esta IP ha alcanzado el umbral de actividades críticas y ha sido bloqueada preventivamente.

Ver detalles del bloqueo:
https://tudominio.com/admin/bot/ipblocklist/5/change/

Ver actividades de esta IP:
https://tudominio.com/admin/bot/suspiciousactivity/?ip_address=192.168.1.100

Si consideras que el bloqueo es incorrecto, puedes desactivarlo desde el panel de administración.

---
Este es un mensaje automático del sistema de seguridad de Studiozens Bot.
```

### Gestionar Bloqueos Automáticos

#### Ver Bloqueos en el Admin

1. Ve a: **Admin → Bot → IPs Bloqueadas**
2. Busca bloqueos con notas que contengan "Auto-bloqueado por el sistema"
3. Verás:
   - IP bloqueada
   - Razón: "Abuso de Límites"
   - Notas: "Auto-bloqueado por el sistema: 3 actividades críticas..."
   - Bloqueado por: (vacío = sistema automático)

#### Desbloquear una IP

**Opción 1: Desde el Admin**
1. Admin → Bot → IPs Bloqueadas
2. Click en la IP
3. Desmarcar "is_active"
4. Guardar

**Opción 2: Desde la API**
```bash
curl -X POST \
  -H "Authorization: Token <tu-admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"ip_address": "192.168.1.100"}' \
  "https://tudominio.com/api/v1/bot/unblock-ip/"
```

---

## 🔧 Comandos de Administración

### 1. Enviar Reporte Diario de Seguridad

Envía un email con estadísticas de las últimas 24 horas.

**Ejecución Manual:**
```bash
python manage.py send_security_report
```

**Programar con Cron (Linux/Mac):**
```cron
# Enviar reporte diario a las 8:00 AM
0 8 * * * cd /path/to/studiozens_project && ./venv/bin/python manage.py send_security_report
```

**Programar con Task Scheduler (Windows):**
1. Abrir "Programador de Tareas"
2. Crear tarea básica
3. Acción: "Iniciar un programa"
4. Programa: `C:\path\to\venv\Scripts\python.exe`
5. Argumentos: `manage.py send_security_report`
6. Directorio: `C:\path\to\studiozens_project`
7. Trigger: Diario a las 8:00 AM

**Ejemplo de Reporte Diario:**
```
Subject: [Reporte Diario] Seguridad del Bot - 2025-01-24

📊 REPORTE DIARIO DE SEGURIDAD - STUDIOZENS BOT 📊
Período: 2025-01-23 08:00 - 2025-01-24 08:00

═══════════════════════════════════════════════════

📈 CONVERSACIONES:
- Total de conversaciones: 1,247
- Conversaciones bloqueadas: 38
- Tasa de bloqueo: 3.05%

⚠️ ACTIVIDADES SOSPECHOSAS:
- Total detectadas: 52
- Críticas: 5
- Altas: 18

🚫 BLOQUEOS:
- Nuevas IPs bloqueadas: 2

🔝 TOP 5 IPs CON MÁS ACTIVIDAD SOSPECHOSA:
1. 192.168.1.100: 12 actividades
2. 10.0.0.50: 8 actividades
3. 172.16.0.10: 5 actividades
4. 192.168.1.200: 4 actividades
5. 10.0.0.100: 3 actividades

═══════════════════════════════════════════════════

Ver panel de administración:
https://tudominio.com/admin/bot/suspiciousactivity/
```

### 2. Revisar y Bloquear IPs Sospechosas

Revisa todas las IPs con actividades críticas y aplica auto-bloqueo si cumplen criterios.

**Ejecución Manual (Dry-Run):**
```bash
python manage.py check_suspicious_ips --dry-run
```

Output:
```
Revisando actividades sospechosas de los últimos 7 días...
MODO DRY-RUN: No se realizarán cambios
Encontradas 5 IPs con actividades críticas
  🔍 IP 192.168.1.100: 4 actividades críticas
  🔍 IP 10.0.0.50: 2 actividades críticas
  🔍 IP 172.16.0.10: 1 actividades críticas
  🔍 IP 192.168.1.200: 3 actividades críticas
  🔍 IP 10.0.0.100: 2 actividades críticas

Ejecuta sin --dry-run para aplicar los bloqueos
```

**Ejecución Real:**
```bash
python manage.py check_suspicious_ips
```

Output:
```
Revisando actividades sospechosas de los últimos 7 días...
Encontradas 5 IPs con actividades críticas
  ✅ IP 192.168.1.100 bloqueada automáticamente
  ℹ️ IP 10.0.0.50 no cumple criterios de bloqueo o ya está bloqueada
  ℹ️ IP 172.16.0.10 no cumple criterios de bloqueo o ya está bloqueada
  ✅ IP 192.168.1.200 bloqueada automáticamente
  ℹ️ IP 10.0.0.100 no cumple criterios de bloqueo o ya está bloqueada

✅ Proceso completado: 2 IPs bloqueadas de 5 analizadas
```

**Opciones del Comando:**
- `--days=N`: Analizar los últimos N días (default: 7)
- `--dry-run`: Modo simulación, no aplica cambios

**Programar con Cron (ejemplo: cada 6 horas):**
```cron
0 */6 * * * cd /path/to/studiozens_project && ./venv/bin/python manage.py check_suspicious_ips
```

---

## 🧪 Testing del Sistema

### Probar Alertas de Email

**Test 1: Verificar Configuración de Email**
```python
# En Django shell
python manage.py shell

from django.core.mail import send_mail
from django.conf import settings

send_mail(
    'Test Email',
    'Este es un email de prueba',
    settings.DEFAULT_FROM_EMAIL,
    ['admin@example.com'],
    fail_silently=False,
)
```

**Test 2: Simular Actividad Crítica**
```python
from bot.models import SuspiciousActivity, AnonymousUser
from bot.suspicious_activity_detector import SuspiciousActivityDetector

# Crear actividad crítica de prueba
SuspiciousActivityDetector.detect_jailbreak_attempt(
    user=None,
    anonymous_user=AnonymousUser.objects.first(),
    ip_address='192.168.1.999',  # IP de prueba
    message='Test jailbreak attempt'
)

# Deberías recibir un email de alerta
```

### Probar Auto-Bloqueo

**Test 1: Verificar Umbral**
```python
from bot.alerts import AutoBlockService

# Simular 3 actividades críticas
for i in range(3):
    SuspiciousActivityDetector.detect_jailbreak_attempt(
        user=None,
        anonymous_user=AnonymousUser.objects.first(),
        ip_address='192.168.1.999',
        message=f'Test jailbreak {i+1}'
    )

# Después de la 3ra, la IP debería bloquearse automáticamente
# Verifica en Admin → Bot → IPs Bloqueadas
```

**Test 2: Verificar Bloqueo Efectivo**
```bash
# Intenta enviar un mensaje desde la IP bloqueada
curl -X POST https://tudominio.com/api/v1/bot/webhook/ \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 192.168.1.999" \
  -d '{"message": "Hola"}'

# Debería retornar HTTP 403 con mensaje de bloqueo
```

---

## 📊 Métricas y Estadísticas

### Monitorear Efectividad del Sistema

#### En el Admin

**Ver Actividades Críticas Bloqueadas:**
```
Admin → Bot → Actividades Sospechosas
Filtrar por: Severidad = Crítica
```

**Ver Auto-Bloqueos:**
```
Admin → Bot → IPs Bloqueadas
Buscar en notas: "Auto-bloqueado por el sistema"
```

#### Via API

**Obtener estadísticas:**
```bash
curl -H "Authorization: Token <admin-token>" \
  "https://tudominio.com/api/v1/bot/suspicious-users/?days=7&min_severity=4"
```

Response incluye:
- IPs con actividades críticas
- Si están bloqueadas o no
- Análisis de patrones

---

## ⚙️ Configuración Avanzada

### Ajustar Sensibilidad del Auto-Bloqueo

**Escenario 1: Demasiados Falsos Positivos**
- Aumentar umbral a **5 actividades críticas**
- Aumentar período a **48 horas**

**Escenario 2: Amenazas Pasando Desapercibidas**
- Reducir umbral a **2 actividades críticas**
- Reducir período a **12 horas**

### Deshabilitar Temporalmente

**Deshabilitar Alertas:**
```
Admin → Bot → Configuración → Alertas de Seguridad
Desmarcar "Habilitar Alertas Críticas"
```

**Deshabilitar Auto-Bloqueo:**
```
Admin → Bot → Configuración → Auto-Bloqueo
Desmarcar "Habilitar Auto-Bloqueo"
```

---

## 🐛 Troubleshooting

### No llegan los emails de alerta

**Check 1: Configuración de Email**
```python
python manage.py shell

from django.core.mail import send_mail
send_mail('Test', 'Test', 'from@example.com', ['to@example.com'])
```

Si falla, revisa `settings.py`:
- `EMAIL_HOST`, `EMAIL_PORT`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`

**Check 2: Usuarios Admin con Email**
```python
from users.models import CustomUser
admins = CustomUser.objects.filter(role=CustomUser.Role.ADMIN)
for admin in admins:
    print(f"{admin.phone_number}: {admin.email}")
```

**Check 3: Alertas Habilitadas**
```python
from bot.models import BotConfiguration
config = BotConfiguration.objects.first()
print(f"Alertas habilitadas: {config.enable_critical_alerts}")
```

### Auto-Bloqueo no funciona

**Check 1: Auto-Bloqueo Habilitado**
```python
from bot.models import BotConfiguration
config = BotConfiguration.objects.first()
print(f"Auto-bloqueo: {config.enable_auto_block}")
print(f"Umbral: {config.auto_block_critical_threshold}")
print(f"Período: {config.auto_block_analysis_period_hours}h")
```

**Check 2: Contar Actividades Críticas**
```python
from bot.models import SuspiciousActivity
from datetime import timedelta
from django.utils import timezone

ip = '192.168.1.100'
since = timezone.now() - timedelta(hours=24)

count = SuspiciousActivity.objects.filter(
    ip_address=ip,
    created_at__gte=since,
    severity=SuspiciousActivity.SeverityLevel.CRITICAL
).count()

print(f"IP {ip}: {count} actividades críticas en 24h")
```

**Check 3: Verificar Logs**
```bash
# En los logs del servidor, buscar:
grep "auto-bloqueada" /path/to/logs/*.log
grep "check_and_auto_block" /path/to/logs/*.log
```

---

## 📚 Resumen

✅ **Alertas por Email:**
- Se envían automáticamente para actividades CRÍTICAS
- Configurables en Admin → Configuración del Bot
- Requieren configuración de email en settings.py

✅ **Auto-Bloqueo:**
- Bloquea IPs con múltiples actividades críticas
- Configurable: umbral y período de análisis
- Notifica a admins cuando bloquea

✅ **Comandos:**
- `send_security_report`: Reporte diario
- `check_suspicious_ips`: Revisar y bloquear IPs

✅ **Monitoreo:**
- Admin de Django con dashboards
- API endpoints para estadísticas
- Logs detallados del sistema
