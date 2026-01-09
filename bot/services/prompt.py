from typing import Any

from django.core.cache import cache

from ..models import BotConfiguration
from ..prompts.master import MASTER_SYSTEM_PROMPT as MASTER_SYSTEM_PROMPT_TEMPLATE
from .context import DataContextService
from .memory import ConversationMemoryService


class PromptOrchestrator:
    """
    Ensambla el Prompt Maestro para Gemini.
    Implementa la arquitectura de 'Agente JSON' donde la IA decide acciones.
    """

    MASTER_SYSTEM_PROMPT = MASTER_SYSTEM_PROMPT_TEMPLATE

    def build_full_prompt(
        self,
        user,
        user_message: str,
        user_id_for_memory: Any = None,
        extra_context: dict | None = None,
    ) -> tuple[str, bool]:
        config = self._get_configuration()
        if not config:
            return "", False

        # Obtener historial completo (hasta 20 mensajes)
        memory_id = user_id_for_memory or (user.id if user else None)
        conversation_history = []
        if memory_id:
            raw_history = ConversationMemoryService.get_conversation_history(memory_id)
            for msg in raw_history:
                role = "USER" if msg["role"] == "user" else "ASSISTANT"
                conversation_history.append(f"{role}: {msg['content']}")

        history_text = "\n".join(conversation_history)

        ctx = DataContextService()

        # Construir el prompt final
        system_instructions = self.MASTER_SYSTEM_PROMPT.format(
            site_name=config.site_name,
            business_context=f"Ubicación: Carrera 64 #1c-87, Cali.\nTel Admin: {config.admin_phone}\nUrl Reservas: {config.booking_url}",
            services_context=ctx.get_services_context(),
            products_context=ctx.get_products_context(),
            client_context=ctx.get_client_context(user),
            booking_url=config.booking_url,
        )

        # Construir contexto adicional si existe (notificaciones previas, etc.)
        extra_context_text = ""
        if extra_context:
            last_notification = extra_context.get("last_notification")
            if last_notification:
                extra_context_text = f"""
--- CONTEXTO ADICIONAL ---
Última notificación enviada al usuario:
  - Tipo: {last_notification.get('event_code', 'N/A')}
  - Asunto: {last_notification.get('subject', 'N/A')}
  - Contenido: {last_notification.get('body', 'N/A')[:200]}...
  - Enviado: {last_notification.get('sent_at', 'N/A')}
  - Canal: {last_notification.get('channel', 'N/A')}

El usuario puede estar respondiendo a esta notificación o haciendo una consulta relacionada.
"""

        # El prompt final combina instrucciones + contexto extra + historial + mensaje actual
        full_prompt = f"""
{system_instructions}
{extra_context_text}
--- HISTORIAL DE CONVERSACIÓN ---
{history_text}

--- MENSAJE ACTUAL DEL USUARIO ---
USER: {user_message}

Recuerda: Responde SOLO en JSON.
"""
        return full_prompt, True

    def _get_configuration(self):
        cache_version = cache.get("bot_config_version", 1)
        cache_key = f"bot_configuration_v{cache_version}"
        config = cache.get(cache_key)
        if config is None:
            config = BotConfiguration.objects.filter(is_active=True).first()
            if config:
                cache.set(cache_key, config, timeout=300)
        return config


__all__ = ["PromptOrchestrator"]
