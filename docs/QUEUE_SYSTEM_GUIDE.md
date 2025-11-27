# 🚀 Sistema de Cola con Rate Limiting para Gemini API

## 📋 Índice

1. [Problema que Resuelve](#problema-que-resuelve)
2. [Arquitectura](#arquitectura)
3. [Configuración](#configuración)
4. [Uso](#uso)
5. [Monitoreo](#monitoreo)
6. [Escalabilidad](#escalabilidad)

---

## Problema que Resuelve

### Límites de Gemini API (Plan Gratuito)
- **15 requests por minuto (RPM)**
- **1,500 requests por día (RPD)**
- **4 millones de tokens por día**

### Escenario Real
Con **40 usuarios** consumiendo sus **25 preguntas diarias**:
- Total: **1,000 requests/día** ✅ Dentro del límite diario
- Problema: Si 20 usuarios escriben al mismo tiempo, se exceden los **15 RPM** ❌

### Solución
Cola inteligente con Celery que:
1. ✅ **Respeta automáticamente el límite de 15 RPM**
2. ✅ **Procesa mensajes en orden** sin bloquear el servidor
3. ✅ **Reintentos automáticos** si hay errores temporales
4. ✅ **Priorización** de usuarios premium sobre anónimos (opcional)
5. ✅ **No pierde mensajes** aunque el servidor se reinicie

---

## Arquitectura

```
┌─────────────┐
│   Usuario   │
│  (Frontend) │
└──────┬──────┘
       │ POST /api/v1/bot/webhook/
       │ {"message": "Hola"}
       ▼
┌──────────────────────────────┐
│   Django (BotWebhookView)    │
│                              │
│  1. Validaciones rápidas     │
│  2. Encolar tarea en Celery  │
│  3. Devolver task_id         │
└──────┬───────────────────────┘
       │ Response: {"task_id": "abc123", "status": "queued"}
       ▼
┌─────────────┐     Polling cada 2s
│   Usuario   │ ◄───────────────────┐
│  (Frontend) │                     │
└──────┬──────┘                     │
       │ GET /api/v1/bot/task-status/abc123/
       ▼                            │
┌──────────────────────────────────┴┐
│   Django (BotTaskStatusView)      │
│                                   │
│  - status: 'pending' (en cola)    │
│  - status: 'processing' (activo)  │
│  - status: 'success' (listo)      │
└───────────────────────────────────┘
       ▲
       │
┌──────┴─────────────────────────────┐
│   Celery Worker (Background)       │
│                                    │
│  1. Verificar rate limit (15 RPM)  │
│  2. Si OK: Llamar a Gemini         │
│  3. Si límite alcanzado: Esperar   │
│  4. Guardar log                    │
│  5. Devolver respuesta             │
└────────────────────────────────────┘
       │ Llamada controlada (max 15/min)
       ▼
┌────────────────┐
│   Gemini API   │
└────────────────┘
```

### Ventana Deslizante (Sliding Window)

El sistema usa una **ventana deslizante de 60 segundos** para controlar el rate limit:

```python
# Ejemplo: Límite de 15 RPM
Minuto 1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] ✅ OK
         ↑                                                    ↑
       0:00                                                 0:55

Minuto 1+: [Request 16 llega en 1:05]
          ↓
          Sistema verifica: ¿Cuántas requests en los últimos 60s?
          - Desde 0:05 hasta 1:05 = Solo 14 requests
          - ✅ Puede proceder (request 1 ya no cuenta)

Minuto 1+: [Request 17 llega en 1:06]
          ↓
          Sistema verifica: ¿Cuántas requests en los últimos 60s?
          - Desde 0:06 hasta 1:06 = 15 requests
          - ❌ Límite alcanzado
          - ⏳ Esperar 2 segundos hasta que request 2 (en 0:08) salga de la ventana
```

Esto permite **uso continuo sin pausas artificiales**, a diferencia de un límite fijo por minuto.

---

## Configuración

### 1. Instalar Redis (Broker de Celery)

Redis almacena la cola de tareas.

#### Windows
```bash
# Descargar Redis desde https://github.com/microsoftarchive/redis/releases
# O usar WSL:
wsl
sudo apt update
sudo apt install redis-server
redis-server
```

#### Linux/Mac
```bash
sudo apt install redis-server   # Ubuntu/Debian
brew install redis              # Mac
redis-server
```

Verificar que Redis está corriendo:
```bash
redis-cli ping
# Debe responder: PONG
```

### 2. Configurar Celery en Django

Ya está configurado en `studiozens/celery.py`. Solo necesitas iniciar el worker.

### 3. Variables de Entorno

Agregar en `.env`:
```bash
# Redis para Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Rate limit de Gemini (opcional, defaults a 15)
GEMINI_MAX_RPM=15
```

### 4. Iniciar Workers de Celery

Abrir **2 terminales**:

**Terminal 1: Worker para mensajes del bot**
```bash
# Windows
.\venv\Scripts\activate
celery -A studiozens worker --loglevel=info --pool=solo -Q bot_messages

# Linux/Mac
source venv/bin/activate
celery -A studiozens worker --loglevel=info -Q bot_messages
```

**Terminal 2: Worker para tareas de mantenimiento (opcional)**
```bash
celery -A studiozens worker --loglevel=info -Q celery
```

### 5. Iniciar Celery Beat (Tareas Programadas)

Para tareas cron como limpieza de logs, reportes diarios, etc.:

```bash
celery -A studiozens beat --loglevel=info
```

---

## Uso

### Modo 1: Sincrónico (Actual - Sin Cola)

**Frontend:**
```javascript
const response = await fetch('/api/v1/bot/webhook/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: 'Hola' })
});

const data = await response.json();
console.log(data.reply); // "¡Hola! ¿En qué puedo ayudarte?"
```

**Pros:**
- ✅ Más simple
- ✅ No requiere polling

**Contras:**
- ❌ Puede exceder 15 RPM de Gemini si hay concurrencia
- ❌ Usuario espera bloqueado 5-20 segundos
- ❌ Si Gemini está lento, el request puede timeout

---

### Modo 2: Asíncrono con Cola (Recomendado)

#### Opción A: Modificar el Webhook para Usar Cola

Cambiar `BotWebhookView.post()` para encolar en lugar de procesar sincrónicamente:

```python
# En bot/views/webhook.py - BotWebhookView.post()

# Después de validaciones...

# Encolar tarea en Celery
from .tasks import process_bot_message_async

task = process_bot_message_async.apply_async(
    kwargs={
        'user_id': user.id if user else None,
        'anonymous_user_id': anon_user.id if anon_user else None,
        'message': user_message,
        'client_ip': client_ip,
        'conversation_history': conversation_history
    },
    queue='bot_messages',  # Cola específica para mensajes
    priority=5 if user else 3  # Prioridad: usuarios > anónimos
)

return Response({
    'task_id': task.id,
    'status': 'queued',
    'message': 'Tu mensaje está siendo procesado...'
}, status=status.HTTP_202_ACCEPTED)
```

**Frontend con Polling:**
```javascript
async function sendMessage(message) {
  // 1. Enviar mensaje y obtener task_id
  const response = await fetch('/api/v1/bot/webhook/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });

  const { task_id, status } = await response.json();

  if (status === 'queued') {
    // 2. Hacer polling hasta que esté listo
    const reply = await pollTaskStatus(task_id);
    return reply;
  }
}

async function pollTaskStatus(taskId) {
  let attempts = 0;
  const maxAttempts = 30; // 30 * 2s = 60s timeout

  while (attempts < maxAttempts) {
    const response = await fetch(`/api/v1/bot/task-status/${taskId}/`);
    const data = await response.json();

    if (data.status === 'success') {
      return data.reply;
    } else if (data.status === 'failure') {
      throw new Error(data.error);
    } else {
      // Aún procesando, mostrar indicador de carga
      console.log('Procesando...');
      await new Promise(resolve => setTimeout(resolve, 2000)); // Esperar 2s
      attempts++;
    }
  }

  throw new Error('Timeout esperando respuesta del bot');
}
```

#### Opción B: Endpoint Dedicado para Cola (Sin Modificar Webhook Actual)

Crear un nuevo endpoint `/api/v1/bot/webhook-async/` que use la cola, y mantener el actual sincrónico para compatibilidad:

```python
class BotWebhookAsyncView(APIView):
    """Versión asíncrona del webhook que usa cola"""
    permission_classes = [AllowAny]

    def post(self, request):
        # ... validaciones ...

        task = process_bot_message_async.apply_async(...)

        return Response({
            'task_id': task.id,
            'status': 'queued'
        }, status=status.HTTP_202_ACCEPTED)
```

---

## Monitoreo

### 1. Flower (Dashboard de Celery)

Instalar:
```bash
pip install flower
```

Iniciar:
```bash
celery -A studiozens flower --port=5555
```

Abrir: http://localhost:5555

**Verás:**
- 📊 Tareas en cola, procesando, completadas
- ⏱️ Tiempos de ejecución
- ❌ Tareas fallidas con detalles
- 🔄 Workers activos
- 📈 Gráficos de throughput

### 2. Logs en Tiempo Real

Ver logs del worker:
```bash
tail -f logs/celery_worker.log
```

Buscar rate limits:
```bash
grep "Rate limit alcanzado" logs/celery_worker.log
```

### 3. Métricas en Redis

Ver tareas pendientes:
```bash
redis-cli
> LLEN celery  # Tareas en cola default
> LLEN bot_messages  # Tareas en cola de bot
```

### 4. Django Admin

Las tareas procesadas se guardan en `BotConversationLog` con metadatos:

```python
# Admin → Bot → Logs de Conversación
log.response_meta = {
    'task_id': 'abc123',
    'processing_time_seconds': 2.5,
    'gemini_latency_ms': 1800,
    'source': 'gemini-rag',
    'tokens': 250
}
```

---

## Escalabilidad

### Escenario 1: Tráfico Bajo (< 10 usuarios concurrentes)

**Configuración:**
- 1 worker de Celery
- Redis en mismo servidor

```bash
celery -A studiozens worker --loglevel=info --concurrency=4
```

### Escenario 2: Tráfico Medio (10-50 usuarios concurrentes)

**Configuración:**
- 2-3 workers de Celery (diferentes procesos)
- Redis dedicado
- Priorización de colas

**Worker 1: Alta prioridad (usuarios registrados)**
```bash
celery -A studiozens worker -Q bot_messages -n worker1@%h --concurrency=8
```

**Worker 2: Baja prioridad (anónimos)**
```bash
celery -A studiozens worker -Q bot_messages_low -n worker2@%h --concurrency=4
```

### Escenario 3: Tráfico Alto (50+ usuarios concurrentes)

**Configuración:**
- 5+ workers distribuidos en múltiples servidores
- Redis Cluster
- RabbitMQ en lugar de Redis (más robusto)
- Monitoreo con Prometheus + Grafana

```bash
# Servidor 1
celery -A studiozens worker -Q bot_messages --concurrency=16 -n worker1@server1

# Servidor 2
celery -A studiozens worker -Q bot_messages --concurrency=16 -n worker2@server2
```

### Ajustar Concurrency

Por defecto, Celery usa `concurrency = CPU_CORES`. Para tareas IO-bound (como llamar a Gemini), puedes aumentarlo:

```bash
# Si tienes 4 cores, puedes usar 16 workers concurrentes
celery -A studiozens worker --concurrency=16
```

### Límite de Throughput

Con **15 RPM de Gemini**:
- **Máximo throughput:** 15 mensajes/minuto = 900 mensajes/hora
- Con 40 usuarios usando 25 mensajes/día = **1,000 mensajes/día** ✅ OK
- Pico máximo: Si todos escriben al mismo tiempo, habrá **delay de cola**

**Ejemplo:** Si llegan 30 mensajes en 1 minuto:
- Primeros 15: Procesados inmediatamente
- Siguientes 15: Esperan en cola ~60 segundos

---

## Priorización de Usuarios

Para dar mejor experiencia a usuarios premium:

```python
# En bot/tasks.py

@shared_task(bind=True, max_retries=5)
def process_bot_message_async(self, user_id=None, ...):
    # ... código actual ...
    pass

# Al encolar en views.py:
task = process_bot_message_async.apply_async(
    kwargs={...},
    queue='bot_messages_high' if user and user.is_premium else 'bot_messages_low',
    priority=10 if user and user.is_premium else 5
)
```

Iniciar workers dedicados:
```bash
# Worker para usuarios premium (más workers)
celery -A studiozens worker -Q bot_messages_high --concurrency=10

# Worker para anónimos (menos workers)
celery -A studiozens worker -Q bot_messages_low --concurrency=4
```

---

## Comandos Útiles

### Ver Estado de Workers
```bash
celery -A studiozens inspect active
celery -A studiozens inspect stats
```

### Purgar Cola
```bash
celery -A studiozens purge
```

### Reiniciar Workers Sin Perder Tareas
```bash
celery -A studiozens control shutdown  # Graceful shutdown
# Luego reiniciar con el comando worker
```

### Ver Tareas Registradas
```bash
celery -A studiozens inspect registered
```

---

## Troubleshooting

### Worker No Procesa Tareas

**Verificar:**
1. Redis está corriendo: `redis-cli ping`
2. Worker está activo: `celery -A studiozens inspect active`
3. Las colas coinciden: Tarea usa `queue='bot_messages'` y worker está escuchando esa cola

### Rate Limit No Se Respeta

**Verificar:**
1. Redis tiene la clave: `redis-cli GET gemini_api_rate_limit`
2. Solo hay un worker por servidor (no múltiples compitiendo)
3. El sistema de ventana deslizante está funcionando

### Tareas Fallan con "User Not Found"

**Causa:** La sesión del usuario expiró entre el momento de encolar y procesar.

**Solución:** Agregar manejo de errores en la tarea:
```python
if user_id:
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("Usuario no encontrado: %s", user_id)
        return {'error': 'Sesión expirada'}
```

---

## Roadmap Futuro

Posibles mejoras:

1. **WebSockets en lugar de Polling**
   - Usar Django Channels
   - Notificar al usuario cuando la respuesta esté lista
   - Mejor UX (sin polling)

2. **Rate Limit Distribuido**
   - Usar Redis Lua scripts para atomicidad
   - Soportar múltiples workers en diferentes servidores

3. **Análisis Predictivo**
   - Predecir carga futura basado en patrones históricos
   - Auto-escalar workers según demanda

4. **Fallback a Otro Modelo**
   - Si Gemini está saturado, usar Claude/GPT como backup
   - Degradación graciosa

---

## Conclusión

Este sistema te permite:

✅ **Respetar el límite de 15 RPM de Gemini** automáticamente
✅ **Manejar 40+ usuarios concurrentes** sin errores
✅ **No perder mensajes** aunque el servidor se reinicie
✅ **Escalar horizontalmente** agregando más workers
✅ **Monitorear** toda la actividad con Flower y logs
✅ **Priorizar** usuarios premium sobre anónimos

El costo de esto es:
- ⚙️ Configurar y mantener Redis + Celery
- 🔄 Cambiar frontend para hacer polling
- 📊 Monitorear workers

**Recomendación:** Si tu tráfico actual es bajo (< 10 usuarios concurrentes), el modo sincrónico actual es suficiente. Implementa la cola cuando notes que empiezas a tener muchos rate limit errors de Gemini.
