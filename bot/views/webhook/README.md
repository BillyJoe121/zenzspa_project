# Módulo Webhook - Estructura Refactorizada

Este módulo contiene las vistas relacionadas con los webhooks del bot, organizadas de forma modular.

## Estructura

```
bot/views/webhook/
├── __init__.py                 # Exporta las vistas principales
├── utils.py                    # Utilidades compartidas
├── bot_webhook.py              # Contenedor: reexporta BotWebhookView
├── bot_webhook_security.py     # Lógica de seguridad y prechecks del webhook
├── bot_webhook_processing.py   # Lógica de IA, logging y handoff
├── health_check.py             # BotHealthCheckView - Health check del servicio
└── whatsapp_webhook.py         # WhatsAppWebhookView - Webhook de WhatsApp/Twilio
```

## Archivos

### `__init__.py`
Exporta las vistas principales para mantener compatibilidad con imports existentes:
- `BotWebhookView`
- `BotHealthCheckView`
- `WhatsAppWebhookView`

### `utils.py`
Contiene funciones de utilidad compartidas por múltiples vistas:
- `get_client_ip(request)`: Obtiene la IP real del cliente de forma segura
- `normalize_chat_response(text)`: Normaliza respuestas para formato de chat

### `bot_webhook.py`
Contenedor para mantener compatibilidad con imports existentes. La lógica se divide en:
- `bot_webhook_security.py`: prechecks, validaciones y deduplicación
- `bot_webhook_processing.py`: IA, logging, handoff y cache de deduplicación

### `health_check.py`
Endpoint de health check:
- Verifica estado del cache (Redis)
- Verifica estado de la base de datos
- Verifica configuración de Gemini API
- Verifica configuración activa del bot
- Opcionalmente verifica workers de Celery

### `whatsapp_webhook.py`
Webhook para mensajes de WhatsApp vía Twilio:
- Recibe mensajes de Twilio
- Valida firma de Twilio (opcional)
- Normaliza números de teléfono
- Gestiona usuarios anónimos de WhatsApp
- Genera respuestas en formato TwiML

## Uso

Los imports existentes siguen funcionando sin cambios:

```python
from bot.views.webhook import BotWebhookView, BotHealthCheckView, WhatsAppWebhookView
```

O importar directamente desde los módulos:

```python
from bot.views.webhook.bot_webhook import BotWebhookView
from bot.views.webhook.health_check import BotHealthCheckView
from bot.views.webhook.whatsapp_webhook import WhatsAppWebhookView
from bot.views.webhook.utils import get_client_ip, normalize_chat_response
```

## Migración

El archivo original `bot/views/webhook.py` (~988 líneas) ha sido:
1. Dividido en módulos especializados más pequeños y manejables
2. Las utilidades compartidas extraídas a `utils.py`
3. Cada vista en su propio archivo para mejor organización
4. Manteniendo compatibilidad total con el código existente

El archivo original se ha renombrado a `webhook.py.old` como respaldo.

## Tests

Todos los tests existentes en `bot/tests/test_views.py` han sido actualizados y pasan correctamente:
- 29 tests pasando
- Funciones de utilidad ahora se importan desde `utils.py`
