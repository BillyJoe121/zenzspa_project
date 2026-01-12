"""
Procesamiento asíncrono de mensajes del bot (Celery).
"""
import logging
import time

from celery import shared_task
from celery.exceptions import Retry
from django.core.cache import cache

from .rate_limit import _check_rate_limit
from ..models import BotConversationLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=5, name="bot.tasks.process_bot_message_async")
def process_bot_message_async(
    self,
    user_id=None,
    anonymous_user_id=None,
    message=None,
    client_ip=None,
    conversation_history=None,
    dedup_id=None
):
    """
    Procesa un mensaje del bot de forma asíncrona respetando el rate limit de Gemini.
    
    Incluye lógica completa de negocio:
    - Rate limiting
    - Llamada a Gemini
    - Detección de escalamiento (Handoff)
    - Scoring de cliente
    - Actualización de historial
    - Logging y Notificaciones
    
    Args:
        user_id: ID del usuario registrado (opcional)
        anonymous_user_id: ID del usuario anónimo (opcional)
        message: Texto del mensaje del usuario
        client_ip: IP del cliente para tracking
        conversation_history: Historial de conversación (opcional, se obtiene de cache si es None)
        dedup_id: ID para deduplicación de requests
    """
    start_time = time.time()

    try:
        # Verificar rate limit ANTES de llamar a Gemini
        from bot import tasks as tasks_pkg
        can_proceed, wait_seconds = tasks_pkg._check_rate_limit()

        if not can_proceed:
            logger.warning(
                "⏳ Rate limit alcanzado (15 RPM). Reintentando en %d segundos. Task: %s",
                wait_seconds,
                self.request.id
            )
            raise self.retry(countdown=wait_seconds, exc=Retry())

        # Importaciones locales
        from ..services import (
            GeminiService, 
            PromptOrchestrator, 
            ConversationMemoryService
        )
        from ..notifications import HandoffNotificationService
        from ..models import AnonymousUser, HumanHandoffRequest
        from ..security import BotSecurityService
        from .cleanup import check_handoff_timeout
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Obtener usuario o anon_user
        user = None
        anon_user = None
        user_id_for_security = None

        if user_id:
            try:
                user = User.objects.get(id=user_id)
                user_id_for_security = user.id
            except User.DoesNotExist:
                logger.error("Usuario no encontrado: %s", user_id)
                return {'error': 'Usuario no encontrado'}

        if anonymous_user_id:
            try:
                anon_user = AnonymousUser.objects.get(id=anonymous_user_id)
                user_id_for_security = f"anon_{anon_user.id}"
            except AnonymousUser.DoesNotExist:
                logger.error("Usuario anónimo no encontrado: %s", anonymous_user_id)
                return {'error': 'Sesión anónima no encontrada'}

        # Construir prompt
        orchestrator = PromptOrchestrator()
        prompt, is_valid = orchestrator.build_full_prompt(
            user=user or anon_user,
            user_message=message,
            user_id_for_memory=user_id_for_security,
        )

        if not is_valid:
            return {'error': 'No active bot configuration'}

        # Llamar a Gemini (Agentic JSON Mode)
        gemini_start = time.time()
        gemini = GeminiService()
        agent_response, meta = gemini.generate_response(prompt)
        gemini_time = (time.time() - gemini_start) * 1000  # ms

        # Extraer datos del agente
        reply_text = agent_response.get("reply_to_user", "")
        analysis = agent_response.get("analysis", {})
        
        action = analysis.get("action", "REPLY")
        toxicity = analysis.get("toxicity_level", 0)
        client_score = analysis.get("customer_score", 0)
        
        # Normalizar texto (simple strip aquí)
        reply_text = reply_text.strip()

        # --- EJECUCIÓN DE ACCIONES DEL AGENTE ---
        
        # CASO 1: BLOQUEO POR TOXICIDAD
        if action == "BLOCK" or toxicity >= 3:
            security = BotSecurityService(user_id_for_security)
            security.block_user("Bloqueo por toxicidad grave (Agente IA Async).")
            
            log = BotConversationLog.objects.create(
                user=user, anonymous_user=anon_user, ip_address=client_ip,
                message=message, response=reply_text,
                was_blocked=True, block_reason="agent_toxicity_block",
                latency_ms=gemini_time,
                response_meta=meta
            )
            return {'reply': "Chat suspendido.", 'meta': {'blocked': True}}

        # CASO 2: HANDOFF
        handoff_data_pending = None
        if action == "HANDOFF":
            # Contexto para el humano
            history = ConversationMemoryService.get_conversation_history(user_id_for_security)
            conversation_context = {
                'last_messages': history[-6:],
                'escalation_message': message,
                'bot_response': reply_text,
                'toxicity_level': toxicity,
                'missing_info': analysis.get("missing_info")
            }
            
            client_interests = {
                'services_mentioned': [analysis.get("intent", "HANDOFF")],
                'score_breakdown': analysis
            }

            handoff_data_pending = {
                'client_score': client_score,
                'escalation_reason': HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
                'conversation_context': conversation_context,
                'client_interests': client_interests,
                'user': user,
                'anonymous_user': anon_user
            }
            
            meta['handoff_detected'] = True
            meta['client_score'] = client_score

        # 3. Guardar Log (Éxito)
        log = BotConversationLog.objects.create(
            user=user,
            anonymous_user=anon_user,
            ip_address=client_ip,
            message=message,
            response=reply_text,
            tokens_used=meta.get('tokens', 0),
            latency_ms=gemini_time,
            was_blocked=False,
            response_meta=meta
        )

        # 4. Crear Handoff si aplica
        if handoff_data_pending:
            handoff_data_pending['conversation_log'] = log
            handoff_request = HumanHandoffRequest.objects.create(**handoff_data_pending)
            
            # Notificar
            try:
                HandoffNotificationService.send_handoff_notification(handoff_request)
                # Programar timeout
                check_handoff_timeout.apply_async(args=[handoff_request.id], countdown=300)
            except Exception as e:
                logger.error("Error enviando notificaciones handoff task: %s", e)
            
            meta['handoff_created'] = True
            meta['handoff_id'] = handoff_request.id

        # 5. Actualizar Historial
        ConversationMemoryService.add_to_history(user_id_for_security, message, reply_text)

        processing_time = time.time() - start_time
        
        response_data = {
            'reply': reply_text,
            'meta': {
                **meta,
                'task_id': self.request.id,
                'processing_time_seconds': round(processing_time, 2),
                'gemini_latency_ms': round(gemini_time, 2),
                'log_id': log.id,
                'agent_analysis': analysis
            }
        }

        # 6. Cachear respuesta
        if dedup_id:
            dedup_key = f"bot:dedup:{dedup_id}"
            cache.set(dedup_key, response_data, timeout=120)

        logger.info(
            "✅ Mensaje procesado async. Task: %s | Usuario: %s | Tiempo: %.2fs",
            self.request.id,
            user.phone_number if user else f"Anon-{anon_user.id}",
            processing_time
        )

        return response_data

    except Retry:
        raise
    except Exception as e:
        logger.exception("Error procesando mensaje en task %s: %s", self.request.id, e)
        # Reintentar si es error transitorio (ej: API error)
        # Si es ValueError (ej: configuración), no reintentar
        if not isinstance(e, (ValueError, TypeError)) and self.request.retries < self.max_retries:
            raise self.retry(countdown=10, exc=e)
        return {
            'error': 'Error procesando mensaje',
            'details': str(e),
            'task_id': self.request.id
        }
