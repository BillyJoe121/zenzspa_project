import logging
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from ...models import BotConversationLog, HumanHandoffRequest
from ...notifications import HandoffNotificationService
from ...services import ConversationMemoryService, GeminiService, PromptOrchestrator
from .utils import normalize_chat_response

logger = logging.getLogger(__name__)


class BotWebhookProcessingMixin:
    def handle_async_mode(self, request, context):
        if not getattr(settings, "BOT_ASYNC_MODE", False):
            return None

        from bot.tasks import process_bot_message_async

        user = context["user"]
        anonymous_user = context["anonymous_user"]
        user_message = context["user_message"]
        client_ip = context["client_ip"]
        dedup_id = context["dedup_id"]
        timings = context["timings"]
        user_id_for_security = context["user_id_for_security"]

        # ID para deduplicación (usamos el mismo dedup_id generado antes)
        dedup_key_id = dedup_id

        task = process_bot_message_async.delay(
            user_id=user.id if user else None,
            anonymous_user_id=anonymous_user.id if anonymous_user else None,
            message=user_message,
            client_ip=client_ip,
            conversation_history=None,  # La tarea lo obtendrá de cache/DB
            dedup_id=dedup_key_id,
        )

        logger.info(
            "Mensaje encolado async. Task: %s | User: %s",
            task.id,
            user_id_for_security,
        )

        return Response(
            {
                "status": "queued",
                "task_id": task.id,
                "message": "Tu mensaje está siendo procesado...",
                "meta": {
                    "queued": True,
                    "timings": timings,
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def process_sync_flow(self, context):
        user = context["user"]
        anonymous_user = context["anonymous_user"]
        user_id_for_security = context["user_id_for_security"]
        user_message = context["user_message"]
        client_ip = context["client_ip"]
        security = context["security"]
        timings = context["timings"]
        dedup_key = context["dedup_key"]
        dedup_window = context["dedup_window"]
        start_time = context["start_time"]

        # ---------------------------------------------------------
        # NIVEL 2: INTELIGENCIA ARTIFICIAL (Costo: Tokens / Latencia)
        # ---------------------------------------------------------

        # Prompt building
        prompt_start = time.time()
        orchestrator = PromptOrchestrator()
        full_prompt, is_valid = orchestrator.build_full_prompt(
            user, user_message, user_id_for_memory=user_id_for_security
        )
        timings["prompt_building"] = time.time() - prompt_start

        if not is_valid:
            return Response(
                {
                    "error": "El servicio de chat no está disponible temporalmente. "
                    "Por favor intenta más tarde."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Gemini API call (Agentic JSON Mode)
        gemini_start = time.time()
        gemini = GeminiService()

        # response_data es un DICT (JSON parseado), meta es DICT
        agent_response, reply_meta = gemini.generate_response(full_prompt)
        timings["gemini_api"] = time.time() - gemini_start

        # Extraer datos del agente
        reply_text = agent_response.get("reply_to_user", "")
        analysis = agent_response.get("analysis", {})

        # Si Gemini (o el mock) indica bloqueo de seguridad nativo
        if reply_meta.get("source") == "security_guardrail":
            action = "BLOCK"
            toxicity = 4
            reply_text = "Contenido bloqueado por seguridad."
        else:
            action = analysis.get("action", "REPLY")
            toxicity = analysis.get("toxicity_level", 0)

        client_score = analysis.get("customer_score", 0)

        # Normalizar texto de respuesta
        reply_text = normalize_chat_response(reply_text)

        # --- EJECUCIÓN DE ACCIONES DEL AGENTE ---

        # CASO 1: BLOQUEO POR TOXICIDAD (Nivel 3)
        if action == "BLOCK" or toxicity >= 3:
            security.block_user("Bloqueo por toxicidad grave (Agente IA).")

            # Registrar bloqueo
            BotConversationLog.objects.create(
                user=user,
                anonymous_user=anonymous_user,
                ip_address=client_ip,
                message=user_message,
                response=reply_text,
                was_blocked=True,
                block_reason="agent_toxicity_block",
                latency_ms=int((time.time() - start_time) * 1000),
                response_meta=reply_meta,
            )

            return Response(
                {
                    "reply": "Este chat ha sido suspendido por incumplimiento de normas.",
                    "meta": {"blocked": True, "reason": "toxicity"},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # CASO 2: HANDOFF (Escalamiento a Humano)
        handoff_data_pending = None
        if action == "HANDOFF":
            # El agente ya verificó que tiene servicio y contacto (si aplica)

            # Contexto para el humano
            conversation_history = ConversationMemoryService.get_conversation_history(user_id_for_security)
            conversation_context = {
                "last_messages": conversation_history[-6:],
                "escalation_message": user_message,
                "bot_response": reply_text,
                "toxicity_level": toxicity,
                "missing_info": analysis.get("missing_info"),
            }

            # Intereses (simplificado, el agente ya hizo el scoring)
            client_interests = {
                "services_mentioned": [analysis.get("intent", "HANDOFF")],
                "score_breakdown": analysis,
            }

            handoff_data_pending = {
                "client_score": client_score,
                "escalation_reason": HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
                "conversation_context": conversation_context,
                "client_interests": client_interests,
            }

            if user:
                handoff_data_pending["user"] = user
            else:
                handoff_data_pending["anonymous_user"] = anonymous_user

            reply_meta["handoff_detected"] = True
            reply_meta["client_score"] = client_score

        # ÉXITO: Mensaje válido y procesado.
        timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}
        reply_meta["timings"] = timings_ms
        reply_meta["agent_analysis"] = analysis  # Guardar análisis completo para debugging

        response_payload = {
            "reply": reply_text,
            "meta": reply_meta,
        }

        if anonymous_user:
            response_payload["session_id"] = str(anonymous_user.session_id)

        # Registrar conversación exitosa
        latency_ms = int((time.time() - start_time) * 1000)

        log_data = {
            "message": user_message,
            "response": reply_text,
            "response_meta": reply_meta,
            "was_blocked": False,
            "block_reason": "",
            "latency_ms": latency_ms,
            "tokens_used": reply_meta.get("tokens", 0),
            "ip_address": client_ip,
        }
        if user:
            log_data["user"] = user
        else:
            log_data["anonymous_user"] = anonymous_user

        conversation_log = BotConversationLog.objects.create(**log_data)

        # Crear Handoff si aplica
        if handoff_data_pending:
            handoff_data_pending["conversation_log"] = conversation_log
            handoff_request = HumanHandoffRequest.objects.create(**handoff_data_pending)

            # Programar timeout de 5 minutos
            from bot.tasks import check_handoff_timeout

            check_handoff_timeout.apply_async(args=[handoff_request.id], countdown=300)

            # Notificar
            try:
                HandoffNotificationService.send_handoff_notification(handoff_request)
            except Exception as e:
                logger.error("Error notificaciones handoff: %s", e)

            reply_meta["handoff_created"] = True
            reply_meta["handoff_id"] = handoff_request.id
            response_payload["meta"] = reply_meta

        # Guardar en historial
        ConversationMemoryService.add_to_history(user_id_for_security, user_message, reply_text)

        # Cachear respuesta para deduplicación
        cache.set(dedup_key, response_payload, timeout=dedup_window * 2)

        return Response(response_payload)
