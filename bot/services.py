import logging
import os
import re
import time
import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from marketplace.models import ProductVariant
from spa.models import Service, Appointment
from .models import BotConfiguration

logger = logging.getLogger(__name__)
CustomUser = get_user_model()
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class _SafeFormatDict(dict):
    def __missing__(self, key):
        logger.warning("Placeholder sin valor para el bot: %s", key)
        return ""


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "N/D"
    return f"${value:,.0f}".replace(",", ".")


class DataContextService:
    """
    Extrae y formatea la información del negocio en tiempo real
    para inyectarla en el prompt del LLM.
    """

    @staticmethod
    def get_services_context() -> str:
        cache_key = 'bot_context:services'
        cached = cache.get(cache_key)
        if cached:
            return cached

        services = Service.objects.filter(is_active=True).order_by('name')
        if not services.exists():
            result = "No hay servicios activos en este momento."
        else:
            lines = []
            for s in services:
                price = _format_money(s.price)
                desc = s.description[:150] + \
                    "..." if len(s.description) > 150 else s.description
                lines.append(f"- {s.name} ({s.duration}min): {price}. {desc}")
            result = "\n".join(lines)

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_products_context() -> str:
        cache_key = 'bot_context:products'
        cached = cache.get(cache_key)
        if cached:
            return cached

        variants = (
            ProductVariant.objects.select_related('product')
            .filter(product__is_active=True)
            .order_by('-stock')[:10]
        )

        if not variants.exists():
            result = "No hay productos publicados actualmente."
        else:
            lines = []
            for v in variants:
                price = _format_money(v.price)
                stock_msg = (
                    f"Stock disponible: {v.stock}"
                    if v.stock > 0
                    else "Actualmente agotado, pronto reabastecemos."
                )
                lines.append(
                    f"- {v.product.name} ({v.name}): {price} | {stock_msg}"
                )
            result = "\n".join(lines)

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_staff_context() -> str:
        cache_key = 'bot_context:staff'
        cached = cache.get(cache_key)
        if cached:
            return cached

        staff = CustomUser.objects.filter(
            role=CustomUser.Role.STAFF,
            is_active=True,
        )[:5]
        if not staff.exists():
            result = "Equipo de terapeutas expertos."
        else:
            result = "\n".join([f"- {person.get_full_name()}" for person in staff])

        cache.set(cache_key, result, timeout=300)
        return result

    @staticmethod
    def get_client_context(user) -> str:
        if not user or not user.is_authenticated:
            return "Cliente Visitante (No logueado)"

        now = timezone.now()
        upcoming = Appointment.objects.filter(
            user=user,
            start_time__gte=now,
            status__in=['CONFIRMED', 'PENDING_PAYMENT']
        ).order_by('start_time').first()

        appt_info = "Sin citas próximas agendadas."
        if upcoming:
            local_time = timezone.localtime(
                upcoming.start_time).strftime("%d/%m a las %H:%M")
            services = upcoming.get_service_names() or "servicios personalizados"
            appt_info = f"Tiene una cita próxima: {services} el {local_time}."

        is_vip = getattr(user, 'is_vip', False)
        first_name_only = user.first_name if hasattr(user, 'first_name') else "Cliente"
        return f"""
        Cliente: {first_name_only}
        Estado VIP: {'Sí' if is_vip else 'No'}
        {appt_info}
        """


class ConversationMemoryService:
    """
    Gestiona el historial de conversación para contexto.
    """

    WINDOW_SIZE = 40  # Aumentado a 40 (aprox 20 pares de preguntas/respuestas)
    CACHE_TIMEOUT = 3600  # 1 hora

    @staticmethod
    def get_conversation_history(user_id: int) -> list[dict]:
        cache_key = f'bot:conversation:{user_id}'
        return cache.get(cache_key, [])

    @staticmethod
    def add_to_history(user_id: int, message: str, response: str):
        cache_key = f'bot:conversation:{user_id}'
        history = ConversationMemoryService.get_conversation_history(user_id)

        history.append({
            'role': 'user',
            'content': message,
            'timestamp': time.time()
        })

        history.append({
            'role': 'assistant',
            'content': response,
            'timestamp': time.time()
        })

        # Mantener solo últimos N mensajes
        history = history[-ConversationMemoryService.WINDOW_SIZE:]
        cache.set(cache_key, history, timeout=ConversationMemoryService.CACHE_TIMEOUT)

    @staticmethod
    def clear_history(user_id: int):
        cache_key = f'bot:conversation:{user_id}'
        cache.delete(cache_key)


class PromptOrchestrator:
    """
    Ensambla el Prompt Maestro para Gemini.
    Implementa la arquitectura de 'Agente JSON' donde la IA decide acciones.
    """

    MASTER_SYSTEM_PROMPT = """
Eres el Asistente Virtual Inteligente de {site_name}.
Tu objetivo es brindar atención al cliente excepcional, vender servicios y filtrar leads cualificados para el equipo humano.

--- INSTRUCCIONES DE FORMATO (CRÍTICO) ---
DEBES RESPONDER SIEMPRE EN FORMATO JSON VÁLIDO.
No incluyas texto fuera del JSON.

Estructura JSON requerida:
{{
  "reply_to_user": "Texto de tu respuesta al usuario (amigable, natural, con emojis).",
  "analysis": {{
    "toxicity_level": 0, // 0=Normal, 1=Leve, 2=Sexual/Inapropiado, 3=Acoso Grave (Bloquear)
    "customer_score": 50, // 0-100 basado en interés y calidad del lead
    "intent": "INFO", // INFO, BOOKING, HANDOFF_REQUEST, CHIT_CHAT
    "missing_info": null, // "SERVICE_INTEREST", "CONTACT_INFO" o null
    "action": "REPLY" // REPLY, ASK_INFO, HANDOFF, BLOCK
  }}
}}

--- REGLAS DE NEGOCIO Y SEGURIDAD ---

1. DETECCIÓN DE TOXICIDAD (Sexual/Acoso):
   - Nivel 0: Conversación normal.
   - Nivel 1: Coqueteo leve o bromas suaves. -> Ignora y reencausa al Spa.
   - Nivel 2: Insinuaciones sexuales claras o preguntas sobre "final feliz". -> ADVERTENCIA.
   - Nivel 3: Acoso explícito, vulgaridad extrema o insistencia sexual tras advertencia. -> ACCIÓN: BLOCK.

2. ESCALAMIENTO A HUMANO (Handoff):
   - El usuario debe solicitar explícitamente hablar con una persona.
   - REQUISITO 1: Debes saber qué servicio/producto le interesa. Si no lo sabes, PREGUNTA antes de escalar.
   - REQUISITO 2: Si es un usuario anónimo (sin nombre/teléfono en contexto), PIDE SU WHATSAPP antes de escalar.
   - Si cumple requisitos -> ACCIÓN: HANDOFF.
   - Si falta info -> ACCIÓN: ASK_INFO (Pregunta lo que falta).

3. SCORING DE CLIENTE (0-100):
   - Base: 10 puntos.
   - +5 puntos por cada pregunta relevante sobre servicios.
   - +20 puntos si menciona presupuesto alto, "VIP", "el mejor servicio".
   - +15 puntos si muestra urgencia ("hoy", "ahora").
   - -20 puntos si es grosero o cortante.

--- CONTEXTO DEL NEGOCIO ---
{business_context}

--- SERVICIOS DISPONIBLES ---
{services_context}

--- PRODUCTOS ---
{products_context}

--- DATOS DEL CLIENTE ---
{client_context}
"""

    def build_full_prompt(self, user, user_message: str, user_id_for_memory=None, extra_context: dict = None) -> tuple[str, bool]:
        config = self._get_configuration()
        if not config:
            return "", False

        # Obtener historial completo (hasta 20 mensajes)
        memory_id = user_id_for_memory or (user.id if user else None)
        conversation_history = []
        if memory_id:
            raw_history = ConversationMemoryService.get_conversation_history(memory_id)
            for msg in raw_history:
                role = "USER" if msg['role'] == 'user' else "ASSISTANT"
                conversation_history.append(f"{role}: {msg['content']}")

        history_text = "\n".join(conversation_history)

        ctx = DataContextService()

        # Construir el prompt final
        system_instructions = self.MASTER_SYSTEM_PROMPT.format(
            site_name=config.site_name,
            business_context=f"Ubicación: Carrera 64 #1c-87, Cali.\nTel Admin: {config.admin_phone}\nUrl Reservas: {config.booking_url}",
            services_context=ctx.get_services_context(),
            products_context=ctx.get_products_context(),
            client_context=ctx.get_client_context(user)
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
        cache_version = cache.get('bot_config_version', 1)
        cache_key = f'bot_configuration_v{cache_version}'
        config = cache.get(cache_key)
        if config is None:
            config = BotConfiguration.objects.filter(is_active=True).first()
            if config:
                cache.set(cache_key, config, timeout=300)
        return config


class GeminiService:
    """Cliente para Google Gemini con soporte JSON nativo."""

    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        self.model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash") # Recomendado para JSON
        self.timeout = 30
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key, http_options={'timeout': self.timeout * 1000})
            except ImportError:
                logger.critical("google-genai no instalado.")
                self.client = None

    def generate_response(self, prompt_text: str) -> tuple[dict, dict]:
        """
        Genera respuesta y la parsea como JSON.
        Retorna (response_dict, metadata_dict).
        """
        if not self.api_key or not self.client:
            return self._fallback_error("Error de configuración API Key")

        try:
            from google.genai import types
            
            # Configuración para forzar JSON
            config = types.GenerateContentConfig(
                temperature=0.3, # Baja temperatura para precisión en JSON
                response_mime_type="application/json",
                max_output_tokens=1000,
            )
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_text,
                config=config,
            )
            
            # Parsear JSON
            try:
                response_json = json.loads(response.text)
            except json.JSONDecodeError:
                logger.error("Gemini no devolvió JSON válido: %s", response.text)
                # Intentar recuperar si hay texto plano
                return {
                    "reply_to_user": response.text,
                    "analysis": {"action": "REPLY", "toxicity_level": 0, "customer_score": 0}
                }, {"source": "fallback_json_error"}

            # Metadata de tokens
            usage = getattr(response, 'usage_metadata', None)
            tokens = 0
            if usage:
                tokens = getattr(usage, 'total_token_count', 0)

            return response_json, {
                "source": "gemini-json",
                "tokens": tokens
            }

        except Exception as e:
            logger.exception("Error en GeminiService")
            return self._fallback_error(str(e))

    def _fallback_error(self, reason):
        return {
            "reply_to_user": "Lo siento, tengo problemas técnicos momentáneos.",
            "analysis": {"action": "REPLY", "toxicity_level": 0, "customer_score": 0}
        }, {"source": "error", "reason": reason}
