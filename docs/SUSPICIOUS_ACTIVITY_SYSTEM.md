# Sistema de Monitoreo y Gestión de Actividad Sospechosa

## 📋 Descripción General

Este sistema te permite monitorear, detectar y gestionar usuarios/IPs sospechosos que abusan del bot. Incluye:

- **Detección automática** de comportamiento sospechoso
- **Bloqueo de IPs** maliciosas
- **Dashboard completo** con estadísticas y análisis
- **Timeline detallado** de actividad de cada usuario/IP
- **Admin interface** para revisar y gestionar incidentes

---

## 🎯 Funcionalidades Principales

### 1. **Detección Automática de Actividades Sospechosas**

El sistema detecta automáticamente:

| Tipo de Actividad | Severidad | Descripción |
|-------------------|-----------|-------------|
| **JAILBREAK_ATTEMPT** | CRÍTICA | Intento de manipular el prompt del sistema |
| **MALICIOUS_CONTENT** | CRÍTICA | Contenido malicioso detectado por Gemini |
| **REPETITIVE_MESSAGES** | ALTA | Mensajes muy similares repetidamente |
| **DAILY_LIMIT_HIT** | ALTA | Usuario alcanzó el límite diario (30/50 msgs) |
| **RATE_LIMIT_HIT** | MEDIA | Usuario enviando mensajes muy rápido |
| **OFF_TOPIC_SPAM** | MEDIA | Spam fuera de tema del spa |
| **EXCESSIVE_TOKENS** | BAJA | Uso excesivo de tokens |
| **IP_ROTATION** | ALTA | Rotación sospechosa de IPs |

### 2. **Bloqueo de IPs**

Razones de bloqueo disponibles:
- `ABUSE` - Abuso de Límites
- `MALICIOUS_CONTENT` - Contenido Malicioso
- `SPAM` - Spam/Flooding
- `FRAUD` - Fraude Detectado
- `MANUAL` - Bloqueo Manual por Admin

Tipos de bloqueo:
- **Permanente**: Sin fecha de expiración
- **Temporal**: Con fecha de expiración específica

---

## 🖥️ Admin de Django

### Acceder al Admin

1. Ve a `https://tudominio.com/admin/`
2. Inicia sesión como ADMIN
3. Navega a la sección **Bot**

### Vistas Disponibles

#### 📊 **Actividades Sospechosas** (`SuspiciousActivity`)

**Vista de Lista:**
- Lista todas las actividades sospechosas detectadas
- **Filtros**: Por tipo, severidad, estado de revisión, fecha
- **Búsqueda**: Por IP, descripción, usuario
- **Colores**: Cada tipo y severidad tiene su color distintivo

**Dashboard Superior** (aparece automáticamente):
```
📈 Estadísticas de los últimos 7 días:
- Actividades por tipo
- Actividades por severidad
- Top 5 IPs con más actividades
- Cantidad de actividades pendientes de revisión
```

**Acciones en Masa:**
- "Marcar como revisadas" - Marca actividades seleccionadas como revisadas
- "Marcar como no revisadas" - Revierte el estado de revisión

**Vista Detallada:**
- Usuario/IP afectado
- Tipo y severidad de la actividad
- Descripción detallada
- Contexto (JSON) con información adicional
- Link al log de conversación (si existe)
- Campo para agregar notas del admin
- Marcar como revisado

#### 🚫 **IPs Bloqueadas** (`IPBlocklist`)

**Vista de Lista:**
- Lista todas las IPs bloqueadas (activas e inactivas)
- **Filtros**: Por estado, razón, fecha
- **Búsqueda**: Por IP, notas
- **Indicadores visuales**: Estado activo/inactivo con colores

**Acciones en Masa:**
- "Activar bloqueos seleccionados"
- "Desactivar bloqueos seleccionados"

**Agregar Bloqueo:**
1. Click en "Agregar IP Bloqueada"
2. Ingresar IP (ej: `192.168.1.100`)
3. Seleccionar razón del bloqueo
4. Agregar notas (opcional pero recomendado)
5. Establecer fecha de expiración (opcional, dejar vacío = permanente)
6. Guardar

**Vista Detallada:**
- IP bloqueada
- Razón del bloqueo
- Notas internas
- Fecha de creación
- Fecha de expiración (o "Permanente")
- Admin que bloqueó la IP

#### 📝 **Logs de Conversación** (`BotConversationLog`)

**Nueva Funcionalidad: Dashboard de IPs Sospechosas**

Ahora cuando entres a ver los logs, verás en la parte superior:

```
⚠️ TOP 10 IPs POR VOLUMEN DE MENSAJES (últimos 7 días)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IP              | Mensajes | Promedio/día | ¿Sospechoso? | Tokens | Bloqueados
192.168.1.100  | 350      | 50.0         | ⚠️ SÍ       | 105k   | 5
10.0.0.50      | 280      | 40.0         | ⚠️ SÍ       | 84k    | 0
172.16.0.10    | 120      | 17.1         | ✓ No        | 36k    | 2
...
```

**Criterio de "Sospechoso":**
- Promedio > 40 mensajes/día

---

## 🔌 Endpoints API (Para Frontend/Dashboard Personalizado)

### 1. **GET `/api/v1/bot/suspicious-users/`**
Obtiene lista de usuarios/IPs sospechosos con análisis completo.

**Parámetros:**
- `days` (opcional, default=7): Período de análisis en días
- `min_severity` (opcional, default=2): Severidad mínima (1=Baja, 2=Media, 3=Alta, 4=Crítica)

**Ejemplo Request:**
```bash
curl -H "Authorization: Token <tu-admin-token>" \
  "https://tudominio.com/api/v1/bot/suspicious-users/?days=7&min_severity=2"
```

**Ejemplo Response:**
```json
{
  "period_days": 7,
  "min_severity": 2,
  "total_suspicious_ips": 5,
  "suspicious_users": [
    {
      "ip_address": "192.168.1.100",
      "is_blocked": false,
      "total_activities": 15,
      "critical_count": 3,
      "high_count": 7,
      "unreviewed_count": 10,
      "last_activity": "2025-01-24T15:30:00Z",
      "registered_users_count": 1,
      "anonymous_users_count": 0,
      "pattern_analysis": {
        "total_messages": 350,
        "total_blocked": 12,
        "avg_messages_per_day": 50.0,
        "block_rate": 3.4,
        "suspicious_activities": 15,
        "critical_activities": 3,
        "is_suspicious": true,
        "suspicion_reasons": [
          "Promedio de 50.0 mensajes/día (límite: 40)",
          "15 actividades sospechosas registradas",
          "3 actividades críticas registradas"
        ]
      },
      "recent_activities": [
        {
          "id": 123,
          "type": "JAILBREAK_ATTEMPT",
          "severity": 4,
          "description": "Intento de jailbreak...",
          "created_at": "2025-01-24T15:30:00Z",
          "participant": "+57 300 123 4567"
        }
      ]
    }
  ]
}
```

### 2. **GET `/api/v1/bot/activity-timeline/`**
Obtiene el historial completo de actividad de un usuario/IP.

**Parámetros:**
- `ip` (opcional): IP address
- `user_id` (opcional): ID del usuario registrado
- `anon_user_id` (opcional): ID del usuario anónimo
- `days` (opcional, default=30): Período de análisis

**Nota:** Debes proporcionar al menos uno de: `ip`, `user_id`, o `anon_user_id`

**Ejemplo Request:**
```bash
curl -H "Authorization: Token <tu-admin-token>" \
  "https://tudominio.com/api/v1/bot/activity-timeline/?ip=192.168.1.100&days=30"
```

**Ejemplo Response:**
```json
{
  "query": {
    "ip_address": "192.168.1.100",
    "user_id": null,
    "anon_user_id": null,
    "days": 30
  },
  "is_blocked": false,
  "block_info": null,
  "pattern_analysis": {
    "total_messages": 350,
    "avg_messages_per_day": 11.7,
    "is_suspicious": true,
    "suspicion_reasons": [...]
  },
  "timeline": {
    "period_days": 30,
    "total_events": 365,
    "conversations_count": 350,
    "suspicious_activities_count": 15,
    "timeline": [
      {
        "type": "conversation",
        "timestamp": "2025-01-01T10:00:00Z",
        "message": "Hola, quiero...",
        "response": "¡Hola! Bienvenid...",
        "was_blocked": false,
        "tokens_used": 450,
        "id": 1001
      },
      {
        "type": "suspicious_activity",
        "timestamp": "2025-01-02T15:30:00Z",
        "activity_type": "JAILBREAK_ATTEMPT",
        "severity": 4,
        "description": "Intento de jailbreak...",
        "reviewed": false,
        "id": 123
      }
    ]
  }
}
```

### 3. **POST `/api/v1/bot/block-ip/`**
Bloquea una IP específica.

**Body:**
```json
{
  "ip_address": "192.168.1.100",
  "reason": "ABUSE",
  "notes": "Usuario abusando del límite diario repetidamente. 15 actividades sospechosas en 7 días.",
  "expires_at": "2025-02-01T00:00:00Z"  // Opcional, null = permanente
}
```

**Razones válidas:**
- `ABUSE`, `MALICIOUS_CONTENT`, `SPAM`, `FRAUD`, `MANUAL`

**Ejemplo Request:**
```bash
curl -X POST \
  -H "Authorization: Token <tu-admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.100",
    "reason": "ABUSE",
    "notes": "Abuso repetido del límite diario"
  }' \
  "https://tudominio.com/api/v1/bot/block-ip/"
```

**Ejemplo Response:**
```json
{
  "success": true,
  "message": "IP 192.168.1.100 bloqueada exitosamente",
  "block": {
    "id": 5,
    "ip_address": "192.168.1.100",
    "reason": "ABUSE",
    "reason_display": "Abuso de Límites",
    "notes": "Abuso repetido del límite diario",
    "blocked_by": "Admin User",
    "created_at": "2025-01-24T16:00:00Z",
    "expires_at": null,
    "is_permanent": true
  }
}
```

### 4. **POST `/api/v1/bot/unblock-ip/`**
Desbloquea una IP previamente bloqueada.

**Body:**
```json
{
  "ip_address": "192.168.1.100"
}
```

**Ejemplo Request:**
```bash
curl -X POST \
  -H "Authorization: Token <tu-admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"ip_address": "192.168.1.100"}' \
  "https://tudominio.com/api/v1/bot/unblock-ip/"
```

**Ejemplo Response:**
```json
{
  "success": true,
  "message": "IP 192.168.1.100 desbloqueada exitosamente"
}
```

---

## 🔄 Flujo de Trabajo Recomendado

### Escenario 1: Revisar Actividades Sospechosas Diarias

1. **Entrar al Admin** → Bot → Actividades Sospechosas
2. **Ver el dashboard** en la parte superior con las estadísticas
3. **Filtrar por "No Revisado"** para ver solo las pendientes
4. **Ordenar por Severidad** (Crítica → Alta → Media)
5. Para cada actividad crítica/alta:
   - Click para ver detalles completos
   - Revisar el contexto (mensaje enviado, respuesta, metadata)
   - Ver el log de conversación asociado (si existe)
   - **Decidir acción:**
     - Si es falso positivo: Marcar como revisado con nota
     - Si es sospechoso: Ir al paso 6
     - Si es abuso claro: Bloquear IP (paso 7)
6. **Investigar más:**
   - Usar el endpoint `/activity-timeline/` con la IP del sospechoso
   - Analizar el patrón completo de comportamiento
   - Verificar si tiene múltiples actividades sospechosas
7. **Bloquear si es necesario:**
   - Admin → Bot → IPs Bloqueadas → Agregar
   - O usar el endpoint `/block-ip/` con la razón y notas
8. **Marcar como revisado** con notas del análisis

### Escenario 2: Usuario Reportado Externalmente

1. **Obtener la IP** del usuario (de los logs del servidor o del reporte)
2. **Consultar el timeline:**
   ```bash
   GET /api/v1/bot/activity-timeline/?ip=X.X.X.X&days=30
   ```
3. **Analizar:**
   - Total de mensajes vs promedio diario
   - Cantidad de bloqueos
   - Actividades sospechosas registradas
   - Timeline completo de interacciones
4. **Verificar en el Admin:**
   - Bot → Logs de Conversación → Buscar por IP
   - Bot → Actividades Sospechosas → Buscar por IP
5. **Tomar decisión:**
   - Bloquear temporal (con `expires_at`)
   - Bloquear permanente
   - Solo monitorear (sin bloqueo, pero agregar notas internas)

### Escenario 3: Detectar Patrones de Fraude

1. **Endpoint de usuarios sospechosos:**
   ```bash
   GET /api/v1/bot/suspicious-users/?days=7&min_severity=3
   ```
2. **Revisar IPs con:**
   - `is_suspicious: true`
   - `critical_count > 0`
   - `pattern_analysis.avg_messages_per_day > 40`
3. **Para cada IP sospechosa:**
   - Obtener timeline completo
   - Verificar si hay rotación de IPs (mismo usuario con múltiples IPs)
   - Analizar horarios de actividad (bots suelen ser 24/7)
4. **Acción:**
   - Bloquear IP primaria
   - Monitorear IPs relacionadas
   - Documentar en notas internas el patrón detectado

---

## 📊 Métricas y Análisis

### ¿Qué hace que un usuario/IP sea "Sospechoso"?

El sistema marca como sospechoso si cumple **uno o más** de estos criterios:

1. **Promedio > 40 mensajes/día**
2. **Tasa de bloqueo > 30%**
3. **Más de 5 actividades sospechosas registradas**
4. **Una o más actividades CRÍTICAS**

### Análisis de Patrones Incluye:

- Total de mensajes en el período
- Promedio de mensajes por día
- Total de mensajes bloqueados
- Tasa de bloqueo (%)
- Total de tokens consumidos
- Cantidad de actividades sospechosas
- Cantidad de actividades críticas
- Razones específicas de sospecha

---

## 🔒 Seguridad y Permisos

### Permisos por Rol:

| Acción | SUPERUSER | ADMIN | STAFF | CLIENT |
|--------|-----------|-------|-------|--------|
| Ver Actividades Sospechosas | ✓ | ✓ | ✓ | ✗ |
| Marcar como Revisado | ✓ | ✓ | ✗ | ✗ |
| Ver IPs Bloqueadas | ✓ | ✓ | ✓ | ✗ |
| Bloquear/Desbloquear IPs | ✓ | ✓ | ✗ | ✗ |
| Ver Logs de Conversación | ✓ | ✓ | ✗ | ✗ |
| Acceder Endpoints API | ✓ | ✓ | ✗ | ✗ |

### Auditoría:

Todas las acciones importantes se registran con:
- Quién realizó la acción (usuario admin)
- Cuándo se realizó (timestamp)
- Notas/razones de la acción

---

## 🚀 Integración con Frontend

### Crear un Dashboard Personalizado

Puedes crear un dashboard React/Vue/Angular que consuma estos endpoints:

**Página: "Usuarios Sospechosos"**
```javascript
// Obtener usuarios sospechosos
const response = await fetch('/api/v1/bot/suspicious-users/?days=7', {
  headers: { 'Authorization': `Token ${adminToken}` }
});
const data = await response.json();

// Mostrar tarjetas con:
// - IP
// - Nivel de sospecha (basado en suspicion_reasons)
// - Actividades recientes
// - Botón "Ver Timeline"
// - Botón "Bloquear IP"
```

**Página: "Timeline de Usuario"**
```javascript
// Obtener timeline al hacer click en una IP
const response = await fetch(
  `/api/v1/bot/activity-timeline/?ip=${ip}&days=30`,
  { headers: { 'Authorization': `Token ${adminToken}` }}
);
const data = await response.json();

// Mostrar timeline visual con:
// - Conversaciones (burbujas de chat)
// - Actividades sospechosas (alertas)
// - Análisis de patrones (gráficos)
// - Botón "Bloquear IP" si no está bloqueada
// - Botón "Desbloquear" si está bloqueada
```

**Acción: Bloquear IP**
```javascript
const blockIP = async (ip, reason, notes) => {
  const response = await fetch('/api/v1/bot/block-ip/', {
    method: 'POST',
    headers: {
      'Authorization': `Token ${adminToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ip_address: ip,
      reason: reason,
      notes: notes,
      expires_at: null  // Permanente
    })
  });

  return await response.json();
};
```

---

## 📝 Ejemplos de Uso

### Ejemplo 1: Investigar IP Sospechosa desde Admin

1. Admin ve en el dashboard de Logs que la IP `192.168.1.100` tiene 350 mensajes en 7 días (50/día)
2. Va a "Actividades Sospechosas" y busca por IP: `192.168.1.100`
3. Ve:
   - 3 intentos de jailbreak (CRÍTICA)
   - 7 límites diarios alcanzados (ALTA)
   - 5 mensajes repetitivos (ALTA)
4. Entra a ver cada actividad y revisa el contexto
5. Determina que es un bot malicioso intentando abusar del sistema
6. Va a "IPs Bloqueadas" → Agregar:
   - IP: `192.168.1.100`
   - Razón: `ABUSE`
   - Notas: "Bot malicioso. 15 actividades sospechosas en 7 días. 3 intentos de jailbreak."
   - Expiración: (vacío = permanente)
7. Guarda. La IP queda bloqueada inmediatamente.
8. Si el usuario intenta acceder de nuevo, recibe:
   ```
   "Tu IP ha sido bloqueada por: Abuso de Límites.
    Contacta al administrador si crees que esto es un error."
   ```

### Ejemplo 2: Usar API para Dashboard Personalizado

```javascript
// Frontend React - Componente SuspiciousUsersPanel
import React, { useEffect, useState } from 'react';

function SuspiciousUsersPanel() {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    fetch('/api/v1/bot/suspicious-users/?days=7&min_severity=3', {
      headers: { 'Authorization': `Token ${localStorage.getItem('adminToken')}` }
    })
    .then(res => res.json())
    .then(data => setUsers(data.suspicious_users));
  }, []);

  const handleBlock = async (ip) => {
    const reason = prompt('Razón del bloqueo (ABUSE, SPAM, FRAUD, etc):');
    const notes = prompt('Notas adicionales:');

    await fetch('/api/v1/bot/block-ip/', {
      method: 'POST',
      headers: {
        'Authorization': `Token ${localStorage.getItem('adminToken')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ip_address: ip, reason, notes })
    });

    alert(`IP ${ip} bloqueada!`);
  };

  return (
    <div>
      <h2>Usuarios Sospechosos (últimos 7 días)</h2>
      {users.map(user => (
        <div key={user.ip_address} className="user-card">
          <h3>{user.ip_address}</h3>
          <p>Actividades: {user.total_activities}
             (Críticas: {user.critical_count}, Altas: {user.high_count})</p>
          <p>Razones de sospecha:</p>
          <ul>
            {user.pattern_analysis.suspicion_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <button onClick={() => handleBlock(user.ip_address)}>
            🚫 Bloquear IP
          </button>
        </div>
      ))}
    </div>
  );
}
```

---

## 🛠️ Troubleshooting

### "No veo actividades sospechosas en el admin"
- Verifica que el sistema esté detectando correctamente (revisa logs del servidor)
- Las actividades se registran automáticamente cuando ocurren bloqueos
- Si no hay bloqueos, no hay actividades sospechosas registradas

### "Bloqueé una IP pero el usuario sigue accediendo"
- Verifica que el bloqueo esté `is_active=True`
- Verifica que no haya expirado (`expires_at`)
- Verifica que la IP sea la correcta (puede estar detrás de un proxy)
- Revisa los logs del servidor para ver la IP real del usuario

### "El endpoint API retorna 403 Forbidden"
- Verifica que el usuario tenga rol ADMIN
- Verifica que el token de autenticación sea correcto
- Los endpoints requieren `IsAdminUser` permission

---

## 📚 Documentación Técnica

### Modelos de Base de Datos

**SuspiciousActivity:**
- `user` / `anonymous_user`: Usuario afectado
- `ip_address`: IP desde donde se realizó la actividad
- `activity_type`: Tipo de actividad (choices)
- `severity`: Nivel de severidad (1-4)
- `description`: Descripción detallada
- `context`: JSON con metadata adicional
- `conversation_log`: FK al log de conversación (opcional)
- `reviewed`: Booleano de si fue revisado
- `reviewed_by` / `reviewed_at`: Auditoría de revisión
- `admin_notes`: Notas del admin

**IPBlocklist:**
- `ip_address`: IP bloqueada (unique)
- `reason`: Razón del bloqueo (choices)
- `notes`: Notas internas
- `blocked_by`: Admin que bloqueó
- `created_at`: Fecha de creación
- `expires_at`: Fecha de expiración (null = permanente)
- `is_active`: Si el bloqueo está activo

### Servicios

**SuspiciousActivityDetector:**
- `check_ip_blocked(ip)`: Verifica si una IP está bloqueada
- `record_activity(...)`: Registra una actividad sospechosa
- `detect_*()`: Métodos específicos para cada tipo de actividad
- `analyze_user_pattern()`: Analiza patrones de comportamiento

**SuspiciousActivityAnalyzer:**
- `get_suspicious_users_summary()`: Resumen de usuarios sospechosos
- `get_activity_timeline()`: Timeline de actividad de un usuario/IP

---

## 🎓 Conclusión

Este sistema te proporciona todas las herramientas necesarias para:
- ✅ Monitorear actividad sospechosa en tiempo real
- ✅ Investigar patrones de abuso
- ✅ Bloquear IPs maliciosas
- ✅ Mantener un registro completo de auditoría
- ✅ Tomar decisiones informadas sobre gestión de fraude

**¿Preguntas? Revisa los logs del sistema o contacta al equipo de desarrollo.**
