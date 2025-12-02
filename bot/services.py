import logging
import os
import re
import time
import json
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from marketplace.models import ProductVariant
from spa.models import Service, Appointment
from .models import BotConfiguration
from .security import sanitize_for_logging, anonymize_pii
from pydantic import BaseModel, ValidationError

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


def _clean_text(value: str, max_length: int = 400) -> str:
    """Elimina caracteres de control, anonimiza PII e inyecciones básicas antes de mandar a LLM."""
    return anonymize_pii(value or "", max_length=max_length)


class LLMResponseSchema(BaseModel):
    reply_to_user: str
    analysis: Dict[str, Any]

    @classmethod
    def validate_payload(cls, payload: dict) -> dict:
        try:
            data = cls.parse_obj(payload)
        except ValidationError as exc:
            logger.warning("LLM response schema validation failed: %s", exc)
            raise
        # Normalizar campos esperados
        analysis = data.analysis or {}
        return {
            "reply_to_user": str(data.reply_to_user)[:1200],
            "analysis": {
                "toxicity_level": int(analysis.get("toxicity_level") or 0),
                "customer_score": int(analysis.get("customer_score") or 10),
                "intent": analysis.get("intent") or "INFO",
                "missing_info": analysis.get("missing_info"),
                "action": analysis.get("action") or "REPLY",
            },
        }


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
                desc_raw = s.description or ""
                desc = _clean_text(desc_raw[:150] + ("..." if len(desc_raw) > 150 else ""))
                name = _clean_text(s.name)
                lines.append(f"- {name} ({s.duration}min): {price}. {desc}")
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
                    f"- {_clean_text(v.product.name)} ({_clean_text(v.name)}): {price} | {_clean_text(stock_msg)}"
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
            result = "\n".join([f"- {_clean_text(person.get_full_name())}" for person in staff])

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
            appt_info = f"Tiene una cita próxima: {_clean_text(services)} el {local_time}."

        is_vip = getattr(user, 'is_vip', False)
        first_name_only = _clean_text(user.first_name if hasattr(user, 'first_name') else "Cliente")
        return f"""
        Cliente: {first_name_only}
        Estado VIP: {'Sí' if is_vip else 'No'}
        {_clean_text(appt_info)}
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
   - +15 puntos si muestra urgencia ("hoy", "ahora").
   - -20 puntos si es grosero o cortante.

4. CANCELACIONES Y RECLAMOS (PQR):
   - Si el cliente desea cancelar un pedido, solicitar reembolso o cambio: Indícale que debe escribir a `servicioalcliente@studiozens.com`.
   - Si tiene una queja o reclamo general: Indícale el mismo correo `servicioalcliente@studiozens.com`.
   - NO intentes resolver estos casos tú mismo, solo redirige.

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
        self.circuit_key = "bot:llm:circuit_until"
        self.failure_key = "bot:llm:failures"
        self.circuit_ttl_seconds = getattr(settings, "BOT_LLM_CIRCUIT_TTL_SECONDS", 120)
        self.circuit_failure_threshold = getattr(settings, "BOT_LLM_CIRCUIT_THRESHOLD", 5)
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key, http_options={'timeout': self.timeout * 1000})
            except ImportError:
                logger.critical("google-genai no instalado.")
                self.client = None

    def generate_response(self, prompt_text: str, max_retries=2) -> tuple[dict, dict]:
        """
        Genera respuesta y la parsea como JSON con sistema de retry inteligente.
        Retorna (response_dict, metadata_dict).

        Args:
            prompt_text: El prompt completo a enviar a Gemini
            max_retries: Número máximo de reintentos en caso de error (default: 2)
        """
        if not self.api_key or not self.client:
            return self._fallback_error("Error de configuración API Key")

        last_error = None
        now_ts = time.time()
        circuit_until = cache.get(self.circuit_key, 0)
        if circuit_until and now_ts < circuit_until:
            logger.warning("Circuito LLM abierto hasta %s", circuit_until)
            return self._fallback_error("Circuito abierto por fallos recientes")

        # Sistema de retry con backoff exponencial
        for attempt in range(max_retries + 1):
            try:
                from google.genai import types

                # Configuración para forzar JSON
                config = types.GenerateContentConfig(
                    temperature=0.3, # Baja temperatura para precisión en JSON
                    response_mime_type="application/json",
                    max_output_tokens=1000,
                )

                start = time.perf_counter()
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt_text,
                    config=config,
                )
                duration = time.perf_counter() - start
                from core.metrics import get_histogram
                get_histogram(
                    "llm_request_duration_seconds",
                    "Latencia de llamadas al LLM",
                    ["status"],
                    buckets=[0.1, 0.3, 0.5, 1, 2, 5],
                ).labels("success").observe(duration)

                # Parsear JSON
                try:
                    response_json = json.loads(response.text)
                except json.JSONDecodeError as json_err:
                    logger.error("Gemini no devolvió JSON válido (intento %d/%d): %s", attempt + 1, max_retries + 1, response.text)

                    # Si es el último intento, intentar recuperar con texto plano
                    if attempt == max_retries:
                        return {
                            "reply_to_user": response.text if response.text else "Lo siento, no pude generar una respuesta válida.",
                            "analysis": {"action": "REPLY", "toxicity_level": 0, "customer_score": 20, "intent": "INFO"}
                        }, {"source": "fallback_json_error", "raw_response": response.text[:200]}

                    # Reintentar
                    time.sleep(0.5 * (attempt + 1))  # Backoff incremental
                    last_error = json_err
                    continue

                # Metadata de tokens
                usage = getattr(response, 'usage_metadata', None)
                tokens = 0
                if usage:
                    tokens = getattr(usage, 'total_token_count', 0)

                # Validar esquema mínimo para evitar inyección o respuestas malformadas
                try:
                    response_json = LLMResponseSchema.validate_payload(response_json)
                except Exception:
                    response_json = self._validate_response_schema(response_json)

                # Éxito - retornar respuesta
                return response_json, {
                    "source": "gemini-json",
                    "tokens": tokens,
                    "attempt": attempt + 1
                }

            except Exception as e:
                last_error = e
                logger.warning("Error en Gemini (intento %d/%d): %s", attempt + 1, max_retries + 1, str(e))

                # Si es el último intento, usar fallback
                if attempt == max_retries:
                    break

                # Backoff exponencial: 1s, 2s, 4s...
                time.sleep(2 ** attempt)

        # Si llegamos aquí, todos los reintentos fallaron
        logger.error("Gemini falló después de %d intentos", max_retries + 1)
        failures = cache.get(self.failure_key, 0) + 1
        cache.set(self.failure_key, failures, timeout=300)
        if failures >= self.circuit_failure_threshold:
            cache.set(self.circuit_key, time.time() + self.circuit_ttl_seconds, timeout=self.circuit_ttl_seconds + 60)
            from core.metrics import get_counter
            get_counter(
                "llm_circuit_breaker_trips_total",
                "Circuit breaker de LLM abierto",
                ["reason"],
            ).labels("failures").inc()
        return self._fallback_error(str(last_error) if last_error else "Error desconocido")

    def _fallback_error(self, reason):
        """
        Fallback mejorado cuando Gemini falla.
        Proporciona respuestas contextuales según el tipo de error.
        """
        import re

        # Intentar proporcionar respuesta contextual según el tipo de error
        fallback_message = "Lo siento, estoy experimentando dificultades técnicas en este momento. "

        # Mensajes específicos según tipo de error
        if "timeout" in reason.lower():
            fallback_message += "El servicio está tardando más de lo habitual. Por favor, intenta nuevamente en unos momentos."
        elif "quota" in reason.lower() or "limit" in reason.lower():
            fallback_message += "Estamos procesando muchas consultas. Por favor, intenta de nuevo en unos minutos."
        elif "auth" in reason.lower() or "api" in reason.lower() or "key" in reason.lower():
            fallback_message += "Hay un problema con la configuración del servicio. Nuestro equipo está trabajando en ello."
        elif "network" in reason.lower() or "connection" in reason.lower():
            fallback_message += "Estamos teniendo problemas de conectividad. Por favor, intenta nuevamente."
        else:
            # Mensaje genérico más amigable
            fallback_message += "Puedes intentar reformular tu pregunta o, si es urgente, solicitar hablar con una persona escribiendo 'quiero hablar con alguien'."

        # Registrar el error para monitoreo
        logger.error("Gemini fallback activado: %s", reason)

        return {
            "reply_to_user": fallback_message,
            "analysis": {
                "action": "REPLY",
                "toxicity_level": 0,
                "customer_score": 20,  # Score bajo pero no cero para registrar interacción
                "intent": "TECHNICAL_ERROR",
                "missing_info": None
            }
        }, {
            "source": "fallback_error",
            "reason": reason,
            "error_type": self._classify_error(reason)
        }

    @staticmethod
    def _validate_response_schema(payload: dict) -> dict:
        """
        Garantiza que la respuesta tenga estructura esperada.
        Si falta algo, se reemplaza con valores seguros.
        """
        if not isinstance(payload, dict):
            return {
                "reply_to_user": "Lo siento, no pude procesar tu solicitud.",
                "analysis": {"toxicity_level": 0, "customer_score": 10, "intent": "INFO", "action": "REPLY", "missing_info": None},
            }

        reply = payload.get("reply_to_user")
        if not isinstance(reply, str) or not reply.strip():
            reply = "Lo siento, no pude procesar tu solicitud."

        analysis = payload.get("analysis") or {}
        if not isinstance(analysis, dict):
            analysis = {}

        return {
            "reply_to_user": reply[:1200],
            "analysis": {
                "toxicity_level": int(analysis.get("toxicity_level") or 0),
                "customer_score": int(analysis.get("customer_score") or 10),
                "intent": analysis.get("intent") or "INFO",
                "missing_info": analysis.get("missing_info"),
                "action": analysis.get("action") or "REPLY",
            },
        }

    def _classify_error(self, reason):
        """Clasifica el tipo de error para métricas."""
        reason_lower = reason.lower()

        if "timeout" in reason_lower:
            return "timeout"
        elif "quota" in reason_lower or "limit" in reason_lower or "429" in reason_lower:
            return "rate_limit"
        elif "auth" in reason_lower or "401" in reason_lower or "403" in reason_lower:
            return "authentication"
        elif "network" in reason_lower or "connection" in reason_lower:
            return "network"
        elif "json" in reason_lower:
            return "json_parse"
        else:
            return "unknown"
