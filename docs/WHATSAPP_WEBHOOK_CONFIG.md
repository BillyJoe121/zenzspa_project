
## 🎯 Resumen

Este documento explica cómo configurar el webhook de WhatsApp en Twilio después de desplegar la aplicación. El sistema permite que tu bot de Gemini responda automáticamente a mensajes de WhatsApp con contexto completo de notificaciones previas.

---

## ✅ Pre-requisitos (Ya completados en código)

- [x] Endpoint `/api/v1/bot/whatsapp/` implementado (`WhatsAppWebhookView`)
- [x] Lógica compartida `process_bot_message()` creada
- [x] `PromptOrchestrator` acepta `extra_context` con notificaciones
- [x] Sistema de notificaciones centralizado funcionando
- [x] Bot de Gemini configurado

---

## 🚀 Configuración Post-Deploy

### Paso 1: Obtener URL del Endpoint

Cuando despliegues tu aplicación, tendrás una URL pública (HTTPS). El endpoint del webhook será:

```
https://tu-dominio.com/api/v1/bot/whatsapp/
```

**Ejemplos**:
- Render: `https://zenzspa.onrender.com/api/v1/bot/whatsapp/`
- Railway: `https://zenzspa-production.up.railway.app/api/v1/bot/whatsapp/`
- Custom: `https://api.zenzspa.com/api/v1/bot/whatsapp/`

**IMPORTANTE**: Debe ser HTTPS (Twilio requiere conexión segura).

---

### Paso 2: Configurar en Twilio Console

1. **Accede a Twilio Console**:
   - Ve a [https://console.twilio.com](https://console.twilio.com)
   - Inicia sesión con tu cuenta

2. **Navega a tu número de WhatsApp**:
   - Sidebar → Messaging → Try it out → Send a WhatsApp message
   - O directamente: Messaging → Senders → WhatsApp senders
   - Selecciona tu número de WhatsApp

3. **Configurar Webhook**:
   En la sección "Messaging" encontrarás:

   **A) Webhook URL for incoming messages**:
   ```
   https://tu-dominio.com/api/v1/bot/whatsapp/
   ```
   - Método: `HTTP POST`

   **B) Fallback URL** (opcional):
   ```
   https://tu-dominio.com/api/v1/bot/whatsapp/
   ```
   - Método: `HTTP POST`
   - Se usa si el webhook principal falla

   **C) Status callback URL** (opcional):
   - Déjalo vacío por ahora
   - Solo necesario si quieres rastrear entregas/lecturas

4. **Guardar cambios**:
   - Click "Save" en la parte inferior

---

### Paso 3: Verificar Configuración

#### Test Rápido:
1. Envía un mensaje de WhatsApp a tu número de Twilio
2. Deberías recibir una respuesta del bot en segundos

#### Ejemplo de interacción:
```
[Usuario WhatsApp]: Hola
[Bot]: ¡Hola! 👋 Soy el asistente virtual de ZenzSpa. ¿En qué puedo ayudarte hoy?

[Usuario]: Quiero reservar una cita
[Bot]: ¡Perfecto! Te puedo ayudar con eso. Para reservar una cita, por favor visita:
https://reservas.zenzspa.com o llámanos al +57 300 123 4567.
```

---

## 🔧 Configuraciones Avanzadas

### A) Validación de Firma de Twilio (Recomendado para Producción)

Para mayor seguridad, puedes activar la validación de firma de Twilio:

1. **En `zenzspa/settings.py`** (o `.env`):
```python
# Activar validación de firma
VALIDATE_TWILIO_SIGNATURE = True

# Asegurarte de tener el Auth Token configurado
TWILIO_AUTH_TOKEN = 'tu_auth_token_de_twilio'
```

2. **Obtener Auth Token**:
   - Twilio Console → Account → API keys & tokens
   - Copia el "Auth Token"

3. **Agregar a variables de entorno**:
```bash
# .env (producción)
VALIDATE_TWILIO_SIGNATURE=True
TWILIO_AUTH_TOKEN=tu_auth_token_aqui
```

**Beneficio**: Garantiza que solo Twilio puede enviar requests al webhook (previene spoofing).

---

### B) Logs y Monitoreo

#### Ver logs en tiempo real:
```bash
# Si usas Render/Railway con Papertrail o similar
tail -f /var/log/app.log | grep "WhatsApp"

# O en consola de tu plataforma
# Buscar mensajes como:
# "WhatsApp webhook recibido. From: +573001234567, MessageSid: SM..."
# "WhatsApp respuesta enviada. To: +573001234567"
```

#### Verificar en Twilio Console:
- Twilio Console → Monitor → Logs → Messaging
- Verás todos los mensajes enviados/recibidos con detalles

#### Verificar en Django Admin:
- Admin → Bot → Bot conversation logs
- Verás todas las conversaciones con metadata completa

---

### C) Rate Limiting y Throttling

El webhook ya incluye throttling automático (compartido con el webhook HTTP):

- **Por minuto**: 10 mensajes/min por usuario
- **Por día**: 30 mensajes/día por usuario, 50 mensajes/día por IP
- **Por IP**: 20 mensajes/min por IP

Si necesitas ajustar:
```python
# bot/throttling.py

class BotRateThrottle(UserRateThrottle):
    rate = '10/min'  # Cambiar aquí

class BotDailyThrottle(BaseThrottle):
    # Ajustar DAILY_LIMIT_PER_USER y DAILY_LIMIT_PER_IP
```

---

## 📊 Cómo Funciona el Sistema

### Flujo Completo:

```
1. Usuario envía mensaje por WhatsApp
   ↓
2. Twilio recibe mensaje y llama a tu webhook
   POST https://tu-dominio.com/api/v1/bot/whatsapp/
   Body: Body="Hola", From="whatsapp:+573001234567"
   ↓
3. WhatsAppWebhookView procesa:
   a) Valida firma de Twilio (si está activado)
   b) Normaliza número: "+573001234567"
   c) Busca usuario por teléfono en BD
   d) Obtiene última notificación enviada al usuario
   ↓
4. Llama a process_bot_message() con extra_context:
   {
     "last_notification": {
       "event_code": "APPOINTMENT_REMINDER_24H",
       "subject": "Recordatorio de cita",
       "body": "Tu cita es mañana...",
       "sent_at": "2024-11-26 10:00:00",
       "channel": "WhatsApp"
     }
   }
   ↓
5. PromptOrchestrator construye prompt con:
   - Instrucciones del sistema
   - Contexto de notificación (si existe)
   - Historial de conversación
   - Mensaje actual
   ↓
6. GeminiService genera respuesta
   ↓
7. WhatsAppWebhookView devuelve TwiML:
   <?xml version="1.0" encoding="UTF-8"?>
   <Response>
       <Message>Respuesta del bot</Message>
   </Response>
   ↓
8. Twilio envía respuesta al usuario por WhatsApp
```

---

## 🎯 Características del Sistema

### ✅ Contexto Inteligente

El bot recibe automáticamente la última notificación enviada al usuario:

**Ejemplo**:
```
[Sistema envía notificación WhatsApp]
"Hola María, tu cita es mañana 15 de Dic a las 2:30 PM para Masaje Sueco."

[Usuario responde por WhatsApp 10 min después]
"Puedo cambiarla para las 4pm?"

[Bot tiene contexto de la notificación y entiende que se refiere a la cita del 15]
"Claro, déjame ayudarte a reagendar tu cita del 15 de diciembre..."
```

### ✅ Usuarios Registrados vs Anónimos

- **Usuario registrado** (tiene cuenta con phone_number):
  - Se identifica automáticamente
  - Tiene acceso a su historial de citas, compras, etc.
  - Conversaciones se asocian a su cuenta

- **Usuario anónimo** (no registrado):
  - Se crea `AnonymousUser` temporal con metadata: `{phone_number, channel: "whatsapp"}`
  - Puede conversar normalmente
  - Si se registra después, puede vincularse manualmente

### ✅ Seguridad Incluida

- Bloqueo por toxicidad (si el bot detecta contenido inapropiado)
- Límites de velocidad (anti-spam)
- Límites diarios (protección de costos)
- Detección de jailbreak attempts
- Validación de firma de Twilio (opcional)
- Registro de IP y metadata para auditoría

### ✅ Handoff a Humano

Si el usuario pide hablar con un humano o el bot no puede resolver:
- Se crea automáticamente un `HumanHandoffRequest`
- Se notifica a los admins por WhatsApp y Email
- El staff puede responder desde el panel de admin
- Timeout de 5 minutos si no hay respuesta

---

## 🐛 Troubleshooting

### Problema: "El webhook no responde"

**Verificar**:
1. La URL es HTTPS (no HTTP)
2. El endpoint está accesible públicamente: `curl https://tu-dominio.com/api/v1/bot/health/`
3. Los logs del servidor muestran requests entrantes
4. No hay errores de CORS (aunque Twilio no debería tenerlos)

**Solución**:
```bash
# Test manual del endpoint
curl -X POST https://tu-dominio.com/api/v1/bot/whatsapp/ \
  -d "Body=Test" \
  -d "From=whatsapp:+573001234567" \
  -d "MessageSid=SMtest123"

# Deberías recibir XML TwiML como respuesta
```

---

### Problema: "Recibo error 403 Forbidden"

**Causa**: Validación de firma de Twilio activada pero firma incorrecta.

**Solución**:
```python
# Temporalmente desactivar validación para debug
VALIDATE_TWILIO_SIGNATURE = False

# Verificar que TWILIO_AUTH_TOKEN coincida con el de Twilio Console
```

---

### Problema: "El bot no tiene contexto de notificaciones"

**Verificar**:
1. Que se hayan enviado notificaciones previas al usuario
2. Que el usuario tenga phone_number en BD
3. Logs de `_get_last_notification()`:
   ```bash
   grep "last_notification" /var/log/app.log
   ```

**Debug**:
```python
# En Django shell
from users.models import CustomUser
from notifications.models import NotificationLog, NotificationTemplate

user = CustomUser.objects.get(phone_number='+573001234567')

# Ver últimas notificaciones
NotificationLog.objects.filter(
    user=user,
    channel=NotificationTemplate.ChannelChoices.WHATSAPP
).order_by('-created_at')[:5]
```

---

### Problema: "Errores de timeout"

**Causa**: Gemini tarda mucho en responder y Twilio hace timeout (10 segundos default).

**Solución Corta**:
```python
# bot/services.py - GeminiService
self.timeout = 8  # Reducir a 8 segundos max
```

**Solución Completa** (modo asíncrono):
```python
# zenzspa/settings.py
BOT_ASYNC_MODE = True

# El webhook responderá "Procesando..." y enviará la respuesta después
# (Requiere configurar Celery workers)
```

---

## 📋 Checklist de Deploy

Antes de configurar el webhook en Twilio:

- [ ] Aplicación desplegada en HTTPS
- [ ] Variables de entorno configuradas:
  - [ ] `TWILIO_ACCOUNT_SID`
  - [ ] `TWILIO_AUTH_TOKEN`
  - [ ] `TWILIO_WHATSAPP_FROM` (ej: `whatsapp:+14155238886`)
  - [ ] `GEMINI_API_KEY`
  - [ ] `SITE_URL` (para links en respuestas)
- [ ] Endpoint accesible: `https://tu-dominio.com/api/v1/bot/whatsapp/`
- [ ] Health check funciona: `https://tu-dominio.com/api/v1/bot/health/`
- [ ] Base de datos migrada (modelos `NotificationLog`, `BotConversationLog`, etc.)
- [ ] Redis/Cache configurado (para historial de conversación)

Después de configurar en Twilio:

- [ ] Enviar mensaje de prueba y verificar respuesta
- [ ] Revisar logs en Twilio Console
- [ ] Revisar logs de Django Admin → Bot conversation logs
- [ ] Probar con notificación previa (enviar notificación y responder por WhatsApp)
- [ ] Verificar handoff a humano funciona
- [ ] Activar validación de firma (producción)

---

## 🎉 ¡Listo!

Una vez completados estos pasos, tu bot de WhatsApp estará funcionando 24/7 respondiendo a usuarios con contexto completo de sus notificaciones y historial.

**Próximos pasos opcionales**:
- Agregar comandos especiales (ej: `/help`, `/status`)
- Implementar botones interactivos de WhatsApp
- Agregar soporte para imágenes/documentos
- Configurar webhooks para status de entrega (delivered/read)
- Integrar con Meta Business API para templates aprobados

---

**Documentación actualizada**: Noviembre 26, 2024
**Versión**: 1.0
