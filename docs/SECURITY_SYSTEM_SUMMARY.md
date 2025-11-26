# 🔒 Sistema de Seguridad y Monitoreo - Resumen Completo

## 📝 Índice

1. [Visión General](#visión-general)
2. [Componentes del Sistema](#componentes-del-sistema)
3. [Quick Start](#quick-start)
4. [Flujos de Trabajo](#flujos-de-trabajo)
5. [Configuración](#configuración)
6. [Documentación Detallada](#documentación-detallada)

---

## Visión General

Este sistema proporciona **protección completa** contra abuso, fraude y comportamiento malicioso en el bot de Zenzspa. Incluye:

### ✅ Características Principales

| Característica | Descripción | Estado |
|----------------|-------------|--------|
| **Tracking de IPs** | Registra IP en cada conversación | ✅ Activo |
| **Detección Automática** | 8 tipos de actividades sospechosas | ✅ Activo |
| **Dashboard Admin** | Vista completa de actividades y estadísticas | ✅ Activo |
| **Bloqueo de IPs** | Manual y automático | ✅ Activo |
| **Alertas por Email** | Notificaciones para actividades críticas | ✅ Activo |
| **Auto-Bloqueo** | Bloqueo automático después de X actividades críticas | ✅ Activo |
| **Endpoints API** | 4 endpoints para dashboard personalizado | ✅ Activo |
| **Comandos Admin** | 2 comandos Django para gestión | ✅ Activo |
| **Timeline de Usuario** | Historial completo de actividad | ✅ Activo |
| **Análisis de Patrones** | Detección de comportamiento anómalo | ✅ Activo |

---

## Componentes del Sistema

### 1. **Modelos de Base de Datos**

#### `SuspiciousActivity`
- Registra todas las actividades sospechosas detectadas
- Tipos: Jailbreak, Límites, Spam, Tokens excesivos, etc.
- Severidad: Baja, Media, Alta, Crítica
- Incluye contexto JSON y referencia al log de conversación

#### `IPBlocklist`
- Gestiona IPs bloqueadas
- Razones: Abuso, Malicioso, Spam, Fraude, Manual
- Soporta bloqueos temporales y permanentes
- Auditoría completa (quién bloqueó, cuándo, notas)

#### `BotConversationLog` (actualizado)
- Ahora incluye campo `ip_address`
- Permite análisis de comportamiento por IP
- Estadísticas agregadas en el admin

### 2. **Servicios**

#### `SuspiciousActivityDetector`
```python
# Ubicación: bot/suspicious_activity_detector.py
- check_ip_blocked(ip)
- record_activity(...)
- detect_jailbreak_attempt(...)
- detect_daily_limit_abuse(...)
- detect_rate_limit_abuse(...)
- detect_repetitive_messages(...)
- detect_off_topic_spam(...)
- analyze_user_pattern(...)
```

#### `SuspiciousActivityAlertService`
```python
# Ubicación: bot/alerts.py
- send_critical_activity_alert(activity)
- send_auto_block_notification(ip, reason, count, block_id)
- send_daily_security_report()
```

#### `AutoBlockService`
```python
# Ubicación: bot/alerts.py
- check_and_auto_block(user, anonymous_user, ip_address)
```

### 3. **Admin de Django**

#### Actividades Sospechosas
- Vista de lista con filtros y búsqueda
- Dashboard con estadísticas de últimos 7 días
- Acciones: Marcar como revisado/no revisado
- Vista detallada con toda la información

#### IPs Bloqueadas
- Gestión completa de bloqueos
- Indicadores visuales de estado
- Acciones: Activar/Desactivar bloqueos
- Auto-asignación de admin que bloquea

#### Logs de Conversación (actualizado)
- Nuevo dashboard con top 10 IPs por volumen
- Indicador de IPs sospechosas (>40 msg/día)
- Búsqueda por IP
- Exportación de datos

### 4. **Endpoints API**

```
GET  /api/v1/bot/analytics/               # Análisis general de uso
GET  /api/v1/bot/suspicious-users/        # Usuarios/IPs sospechosos
GET  /api/v1/bot/activity-timeline/       # Timeline de usuario/IP
POST /api/v1/bot/block-ip/                # Bloquear IP
POST /api/v1/bot/unblock-ip/              # Desbloquear IP
```

### 5. **Comandos de Administración**

```bash
# Enviar reporte diario de seguridad
python manage.py send_security_report

# Revisar y bloquear IPs sospechosas
python manage.py check_suspicious_ips [--days=7] [--dry-run]
```

---

## Quick Start

### Paso 1: Configurar Emails (Requerido para Alertas)

En `zenzspa/settings.py`:

```python
# Configuración de Email (ejemplo con Gmail)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'noreply@zenzspa.com'
SITE_URL = 'https://tudominio.com'  # Para links en emails

# Admins que recibirán alertas (alternativo)
ADMINS = [
    ('Admin Name', 'admin@example.com'),
]
```

### Paso 2: Verificar Configuración en Admin

1. Ve a: **Admin → Bot → Configuración del Bot**
2. Sección **"Alertas de Seguridad"**:
   - ✅ Habilitar Alertas Críticas
3. Sección **"Auto-Bloqueo"**:
   - ✅ Habilitar Auto-Bloqueo
   - Umbral: 3 actividades críticas (recomendado)
   - Período: 24 horas (recomendado)

### Paso 3: Configurar Admin Emails

Asegúrate de que los usuarios ADMIN tengan email:
```
Admin → Users → Usuarios
- Verificar que admins tengan email configurado
```

### Paso 4: Probar el Sistema

**Test de Alertas:**
```bash
python manage.py shell
```
```python
from bot.suspicious_activity_detector import SuspiciousActivityDetector
from bot.models import AnonymousUser

# Simular actividad crítica
anon = AnonymousUser.objects.first()
SuspiciousActivityDetector.detect_jailbreak_attempt(
    user=None,
    anonymous_user=anon,
    ip_address='192.168.1.999',
    message='Test jailbreak'
)

# Deberías recibir un email de alerta
```

**Test de Auto-Bloqueo:**
```python
# Simular 3 actividades críticas
for i in range(3):
    SuspiciousActivityDetector.detect_jailbreak_attempt(
        user=None,
        anonymous_user=anon,
        ip_address='192.168.1.999',
        message=f'Test {i+1}'
    )

# Después de la 3ra, la IP debería auto-bloquearse
# Verifica en: Admin → Bot → IPs Bloqueadas
```

---

## Flujos de Trabajo

### Flujo 1: Detección Automática y Alertas

```mermaid
Usuario → Bot
  ↓
Detecta Actividad Sospechosa (ej: Jailbreak)
  ↓
Registra en SuspiciousActivity (CRÍTICA)
  ↓
[ALERTA EMAIL] → Admins
  ↓
Verifica Auto-Bloqueo
  ↓
Si cumple umbral (3 en 24h):
  ↓
  → Bloquea IP automáticamente
  → [EMAIL] Notifica a Admins
```

### Flujo 2: Revisión Manual de Admin

```mermaid
Admin → Django Admin
  ↓
Ver Dashboard de Actividades Sospechosas
  ↓
Filtrar: Críticas + No Revisadas
  ↓
Click en Actividad
  ↓
Revisar: Contexto, IP, Usuario, Historial
  ↓
Decisión:
  - Falso Positivo → Marcar como Revisado
  - Sospechoso → Ver Timeline Completo
  - Abuso Claro → Bloquear IP
```

### Flujo 3: Investigación de IP Sospechosa

```mermaid
Admin detecta IP sospechosa (ej: desde Dashboard)
  ↓
Admin → IPs Bloqueadas o API
  ↓
GET /api/v1/bot/activity-timeline/?ip=X.X.X.X&days=30
  ↓
Analiza:
  - Total mensajes
  - Actividades sospechosas
  - Patrones temporales
  - Tasa de bloqueo
  ↓
Decisión:
  - Bloqueo Temporal (expires_at)
  - Bloqueo Permanente
  - Solo Monitorear
```

---

## Configuración

### Configuración de Sensibilidad

#### Configuración Recomendada (Balanceada)
```
Auto-Bloqueo: ✅ Habilitado
Umbral: 3 actividades críticas
Período: 24 horas
Alertas: ✅ Habilitadas
```

#### Configuración Estricta (Alta Seguridad)
```
Auto-Bloqueo: ✅ Habilitado
Umbral: 2 actividades críticas
Período: 12 horas
Alertas: ✅ Habilitadas
```

#### Configuración Permisiva (Menos Restrictiva)
```
Auto-Bloqueo: ✅ Habilitado
Umbral: 5 actividades críticas
Período: 48 horas
Alertas: ✅ Habilitadas
```

### Programar Tareas Automáticas

#### Linux/Mac (Cron)

```cron
# Reporte diario a las 8:00 AM
0 8 * * * cd /path/to/zenzspa_project && ./venv/bin/python manage.py send_security_report

# Revisar IPs cada 6 horas
0 */6 * * * cd /path/to/zenzspa_project && ./venv/bin/python manage.py check_suspicious_ips
```

#### Windows (Task Scheduler)

**Reporte Diario:**
- Programa: `C:\path\to\venv\Scripts\python.exe`
- Argumentos: `manage.py send_security_report`
- Directorio: `C:\path\to\zenzspa_project`
- Trigger: Diario a las 8:00 AM

**Revisar IPs:**
- Programa: `C:\path\to\venv\Scripts\python.exe`
- Argumentos: `manage.py check_suspicious_ips`
- Directorio: `C:\path\to\zenzspa_project`
- Trigger: Cada 6 horas

---

## Documentación Detallada

Para información detallada sobre cada componente, consulta:

### 📄 Documentos Disponibles

1. **[SUSPICIOUS_ACTIVITY_SYSTEM.md](SUSPICIOUS_ACTIVITY_SYSTEM.md)**
   - Sistema completo de monitoreo de usuarios sospechosos
   - Dashboard admin y endpoints API
   - Bloqueo manual de IPs
   - Ejemplos de uso

2. **[ALERTS_AND_AUTO_BLOCK.md](ALERTS_AND_AUTO_BLOCK.md)**
   - Configuración de alertas por email
   - Sistema de auto-bloqueo
   - Comandos de administración
   - Testing y troubleshooting

### 🎯 Accesos Rápidos

#### Admin de Django
```
https://tudominio.com/admin/bot/
- Configuración del Bot
- Actividades Sospechosas
- IPs Bloqueadas
- Logs de Conversación
```

#### Endpoints API
```
https://tudominio.com/api/v1/bot/
- analytics/
- suspicious-users/
- activity-timeline/
- block-ip/
- unblock-ip/
```

---

## 🎓 Casos de Uso Comunes

### Caso 1: Revisar Actividades Diarias

1. Abrir Admin → Bot → Actividades Sospechosas
2. Ver dashboard con estadísticas de últimos 7 días
3. Filtrar por "No Revisado" + "Crítica" o "Alta"
4. Revisar cada una y tomar acción

### Caso 2: Investigar IP Reportada

1. Admin → Bot → Actividades Sospechosas
2. Buscar por IP: `192.168.1.100`
3. Ver todas las actividades de esa IP
4. Si hay patrón de abuso: Bloquear
5. Admin → Bot → IPs Bloqueadas → Agregar

### Caso 3: Análisis de Patrones Semanales

1. Ejecutar comando:
   ```bash
   python manage.py check_suspicious_ips --days=7 --dry-run
   ```
2. Revisar output de IPs sospechosas
3. Para cada IP con alto conteo:
   - Ver timeline completo
   - Decidir acción

### Caso 4: Desbloquear Usuario Legítimo

1. Usuario reporta que está bloqueado
2. Admin → Bot → IPs Bloqueadas
3. Buscar por IP del usuario
4. Revisar motivo del bloqueo
5. Si fue error:
   - Desmarcar "is_active"
   - Guardar
6. Notificar al usuario

---

## 📊 Métricas de Éxito

### KPIs del Sistema

- **Tasa de Detección**: % de actividades maliciosas detectadas
- **Tasa de Bloqueo**: % de IPs bloqueadas / total de IPs únicas
- **Falsos Positivos**: % de bloqueos revertidos
- **Tiempo de Respuesta**: Tiempo promedio entre detección y bloqueo
- **Efectividad de Auto-Bloqueo**: % de amenazas neutralizadas automáticamente

### Monitorear en Admin

```
Admin → Bot → Actividades Sospechosas
- Total de actividades por tipo
- Total de actividades por severidad
- Top IPs con más actividad sospechosa
- Actividades pendientes de revisión
```

---

## 🚀 Roadmap Futuro (Opcional)

Posibles mejoras a considerar:

1. **Geolocalización de IPs**: Detectar patrones geográficos de abuso
2. **Machine Learning**: Detección predictiva de comportamiento anómalo
3. **Integración con CDN**: Bloqueo a nivel de Cloudflare/AWS
4. **Dashboard React**: Dashboard personalizado con gráficos en tiempo real
5. **Webhooks**: Notificaciones a Slack/Discord cuando hay alertas críticas
6. **Rate Limiting Dinámico**: Ajustar límites basados en comportamiento
7. **Whitelist de IPs**: IPs confiables que nunca se bloquean
8. **Análisis de Texto**: NLP para detectar patrones en mensajes maliciosos

---

## 📞 Soporte

**¿Problemas con el sistema?**

1. Revisa la sección de **Troubleshooting** en [ALERTS_AND_AUTO_BLOCK.md](ALERTS_AND_AUTO_BLOCK.md)
2. Revisa los logs del servidor:
   ```bash
   grep "SuspiciousActivity" /path/to/logs/*.log
   grep "auto-block" /path/to/logs/*.log
   ```
3. Verifica la configuración en Admin → Bot → Configuración

**Contacto:**
- Email: tu-email@example.com
- Slack: #zenzspa-bot-security

---

## ✅ Checklist de Implementación

Antes de ir a producción, verifica:

- [ ] Emails configurados en `settings.py`
- [ ] Admins tienen emails configurados
- [ ] Alertas críticas habilitadas
- [ ] Auto-bloqueo configurado (umbral y período)
- [ ] Test de alerta enviado y recibido
- [ ] Test de auto-bloqueo funciona
- [ ] Comandos de administración probados
- [ ] Tareas programadas configuradas (cron/scheduler)
- [ ] Dashboard admin accesible
- [ ] Endpoints API funcionando
- [ ] Documentación revisada por el equipo

---

## 🎉 Conclusión

Este sistema proporciona una **capa completa de seguridad** para el bot de Zenzspa, con:

- ✅ Detección automática de amenazas
- ✅ Alertas en tiempo real
- ✅ Auto-bloqueo inteligente
- ✅ Dashboard completo para administración
- ✅ API para integraciones personalizadas
- ✅ Comandos para automatización

**El bot ahora está protegido contra:**
- 🚫 Intentos de jailbreak
- 🚫 Abuso de límites
- 🚫 Spam y flooding
- 🚫 Contenido malicioso
- 🚫 Comportamiento fraudulento

¡Todo listo para producción! 🚀
