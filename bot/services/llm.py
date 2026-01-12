import json
import logging
import os
import time
from typing import Any, Dict

from django.conf import settings
from django.core.cache import cache
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


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


class GeminiService:
    """Cliente para Google Gemini con soporte JSON nativo."""

    def __init__(self):
        self.api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        self.model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")  # Recomendado para JSON
        self.timeout = 30
        self.client = None
        self.circuit_key = "bot:llm:circuit_until"
        self.failure_key = "bot:llm:failures"
        self.circuit_ttl_seconds = getattr(settings, "BOT_LLM_CIRCUIT_TTL_SECONDS", 120)
        self.circuit_failure_threshold = getattr(settings, "BOT_LLM_CIRCUIT_THRESHOLD", 5)

        if self.api_key:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key, http_options={"timeout": self.timeout * 1000})
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
                    temperature=0.3,  # Baja temperatura para precisión en JSON
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
                from core.infra.metrics import get_histogram

                get_histogram(
                    "llm_request_duration_seconds",
                    "Latencia de llamadas al LLM",
                    ["status"],
                    buckets=[0.1, 0.3, 0.5, 1, 2, 5],
                ).labels("success").observe(duration)

                # Parsear JSON
                try:
                    response_json = json.loads(response.text)
                except json.JSONDecodeError:
                    logger.error(
                        "Gemini no devolvió JSON válido (intento %d/%d): %s",
                        attempt + 1,
                        max_retries + 1,
                        response.text,
                    )

                    # Si es el último intento, intentar recuperar con texto plano
                    if attempt == max_retries:
                        return (
                            {
                                "reply_to_user": response.text if response.text else "Lo siento, no pude generar una respuesta válida.",
                                "analysis": {"action": "REPLY", "toxicity_level": 0, "customer_score": 20, "intent": "INFO"},
                            },
                            {"source": "fallback_json_error", "raw_response": response.text[:200]},
                        )

                    # Reintentar
                    time.sleep(0.5 * (attempt + 1))  # Backoff incremental
                    last_error = "json_decode"
                    continue

                # Metadata de tokens
                usage = getattr(response, "usage_metadata", None)
                tokens = getattr(usage, "total_token_count", 0) if usage else 0

                # Validar esquema mínimo para evitar inyección o respuestas malformadas
                try:
                    response_json = LLMResponseSchema.validate_payload(response_json)
                except Exception:
                    response_json = self._validate_response_schema(response_json)

                # Éxito - retornar respuesta
                return response_json, {
                    "source": "gemini-json",
                    "tokens": tokens,
                    "attempt": attempt + 1,
                }

            except Exception as e:
                last_error = e
                logger.warning("Error en Gemini (intento %d/%d): %s", attempt + 1, max_retries + 1, str(e))

                # Si es el último intento, usar fallback
                if attempt == max_retries:
                    break

                # Backoff exponencial: 1s, 2s, 4s...
                time.sleep(2**attempt)

        # Si llegamos aquí, todos los reintentos fallaron
        logger.error("Gemini falló después de %d intentos", max_retries + 1)
        failures = cache.get(self.failure_key, 0) + 1
        cache.set(self.failure_key, failures, timeout=300)
        if failures >= self.circuit_failure_threshold:
            cache.set(self.circuit_key, time.time() + self.circuit_ttl_seconds, timeout=self.circuit_ttl_seconds + 60)
            from core.infra.metrics import get_counter

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

        # Intentar proporcionar respuesta contextual según el tipo de error
        fallback_message = "Lo siento, estoy experimentando dificultades técnicas en este momento. "

        # Mensajes específicos según tipo de error
        reason_lower = reason.lower() if isinstance(reason, str) else ""
        if "timeout" in reason_lower:
            fallback_message += "El servicio está tardando más de lo habitual. Por favor, intenta nuevamente en unos momentos."
        elif "quota" in reason_lower or "limit" in reason_lower:
            fallback_message += "Estamos procesando muchas consultas. Por favor, intenta de nuevo en unos minutos."
        elif "auth" in reason_lower or "api" in reason_lower or "key" in reason_lower:
            fallback_message += "Hay un problema con la configuración del servicio. Nuestro equipo está trabajando en ello."
        elif "network" in reason_lower or "connection" in reason_lower:
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
                "missing_info": None,
            },
        }, {"source": "fallback_error", "reason": reason, "error_type": self._classify_error(reason)}

    @staticmethod
    def _validate_response_schema(payload: dict) -> dict:
        """
        Garantiza que la respuesta tenga estructura esperada.
        Si falta algo, se reemplaza con valores seguros.
        """
        if not isinstance(payload, dict):
            return {
                "reply_to_user": "Lo siento, no pude procesar tu solicitud.",
                "analysis": {
                    "toxicity_level": 0,
                    "customer_score": 10,
                    "intent": "INFO",
                    "action": "REPLY",
                    "missing_info": None,
                },
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

    @staticmethod
    def _classify_error(reason):
        """Clasifica el tipo de error para métricas."""
        reason_lower = reason.lower() if isinstance(reason, str) else ""

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


__all__ = ["LLMResponseSchema", "GeminiService"]
