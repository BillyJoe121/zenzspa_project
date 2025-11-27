"""
Servicios compartidos para procesamiento de mensajes del bot.
Usado tanto por el webhook HTTP como por el webhook de WhatsApp.
"""
import hashlib
import logging
import time
import re

from django.core.cache import cache
from django.conf import settings

from .services import PromptOrchestrator, GeminiService, ConversationMemoryService
from .security import BotSecurityService
from .models import BotConversationLog, HumanHandoffRequest
from .notifications import HandoffNotificationService
from .suspicious_activity_detector import SuspiciousActivityDetector

logger = logging.getLogger(__name__)


def normalize_chat_response(text: str) -> str:
    """
    Normaliza la respuesta para formato de chat con píldoras.
    - Convierte \\n\\n a \\n (un solo salto)
    - Asegura espacio después de cada \\n
    - Divide párrafos largos en fragmentos más cortos
    """
    # 1. Normalizar múltiples saltos a uno solo
    text = re.sub(r'\n\n+', '\n', text)

    # 2. Asegurar espacio después de \n si no lo hay
    text = re.sub(r'\n([^\s])', r'\n\1', text)

    # 3. Dividir oraciones largas (opcional, más agresivo)
    # Si un párrafo tiene más de 150 caracteres, intentar dividirlo
    paragraphs = text.split('\n')
    normalized = []

    for para in paragraphs:
        if len(para) > 150:
            # Dividir por puntos seguidos de espacio
            sentences = re.split(r'(\. )', para)
            current_chunk = ""

            for i, part in enumerate(sentences):
                current_chunk += part
                # Si es un punto o llegamos a ~100 chars, hacer corte
                if part == '. ' or (len(current_chunk) > 100 and i < len(sentences) - 1):
                    normalized.append(current_chunk.strip())
                    current_chunk = ""

            if current_chunk:
                normalized.append(current_chunk.strip())
        else:
            normalized.append(para)

    return '\n'.join(normalized)


def process_bot_message(
    user,
    anonymous_user,
    user_message: str,
    client_ip: str,
    user_id_for_security: str,
    extra_context: dict = None
):
    """
    Procesa un mensaje del bot, compartido entre webhook HTTP y WhatsApp.

    Args:
        user: CustomUser o None
        anonymous_user: AnonymousUser o None
        user_message: Mensaje del usuario (ya validado)
        client_ip: IP del cliente
        user_id_for_security: ID para sistema de seguridad
        extra_context: Contexto adicional (ej: notificación previa para WhatsApp)

    Returns:
        dict con:
            - reply: Texto de respuesta
            - meta: Metadatos
            - session_id: Solo si es anónimo
            - handoff_created: bool
            - handoff_id: int (opcional)
    """
    security = BotSecurityService(user_id_for_security)
    start_time = time.time()
    timings = {}

    # ---------------------------------------------------------
    # NIVEL 1: BLOQUEOS PREVIOS
    # ---------------------------------------------------------
    security_start = time.time()

    # 0. CHEQUEO DE IP BLOQUEADA
    ip_blocked, ip_block_reason = SuspiciousActivityDetector.check_ip_blocked(client_ip)
    if ip_blocked:
        raise PermissionError(ip_block_reason)

    # 1. ¿Está el usuario castigado?
    is_blocked, reason = security.is_blocked()
    if is_blocked:
        raise PermissionError(reason)

    # 2. Validación de longitud
    valid_len, len_error = security.validate_input_length(user_message)
    if not valid_len:
        raise ValueError(len_error)

    # 2.5 Validación de contenido (Jailbreak)
    valid_content, content_error = security.validate_input_content(user_message)
    if not valid_content:
        SuspiciousActivityDetector.detect_jailbreak_attempt(
            user, anonymous_user, client_ip, user_message
        )
        raise ValueError(content_error)

    # 2.6 LÍMITE DIARIO
    exceeded_daily, daily_error = security.check_daily_limit(ip_address=client_ip)
    if exceeded_daily:
        match = re.search(r'(\d+)/(\d+)', daily_error)
        current_count = int(match.group(1)) if match else 50
        limit = int(match.group(2)) if match else 50

        SuspiciousActivityDetector.detect_daily_limit_abuse(
            user, anonymous_user, client_ip, current_count, limit
        )
        raise PermissionError(daily_error)

    # DEDUPLICACIÓN
    dedup_window = 10
    dedup_id = hashlib.sha256(
        f"{user_id_for_security}:{user_message}:{int(time.time() / dedup_window)}".encode()
    ).hexdigest()[:16]
    dedup_key = f"bot:dedup:{dedup_id}"

    cached_response = cache.get(dedup_key)
    if cached_response:
        logger.info("Request duplicado para user_id %s. Devolviendo cache.", user_id_for_security)
        return cached_response

    # 3. CHEQUEO DE VELOCIDAD
    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES + 1):
        try:
            if security.check_velocity():
                SuspiciousActivityDetector.detect_rate_limit_abuse(
                    user, anonymous_user, client_ip
                )
                raise PermissionError("Estás enviando mensajes demasiado rápido. Acceso pausado por 24h.")

            # 4. CHEQUEO DE REPETICIÓN
            if security.check_repetition(user_message):
                SuspiciousActivityDetector.detect_repetitive_messages(
                    user, anonymous_user, client_ip, user_message
                )
                raise PermissionError("Hemos detectado mensajes repetitivos. Acceso pausado por 24h.")

            break
        except BlockingIOError:
            if attempt < MAX_RETRIES:
                logger.warning(
                    "Lock contention para usuario %s, reintentando (%d/%d)",
                    user_id_for_security, attempt + 1, MAX_RETRIES
                )
                time.sleep(0.1 * (attempt + 1))
                continue
            else:
                raise RuntimeError("El sistema está experimentando alta carga. Intenta en unos segundos.")

    timings['security_checks'] = time.time() - security_start

    # ---------------------------------------------------------
    # NIVEL 2: INTELIGENCIA ARTIFICIAL
    # ---------------------------------------------------------

    # Prompt building
    prompt_start = time.time()
    orchestrator = PromptOrchestrator()

    # Pasar extra_context al orquestador si existe
    full_prompt, is_valid = orchestrator.build_full_prompt(
        user,
        user_message,
        user_id_for_memory=user_id_for_security,
        extra_context=extra_context  # Aquí pasamos el contexto adicional
    )
    timings['prompt_building'] = time.time() - prompt_start

    if not is_valid:
        raise RuntimeError("El servicio de chat no está disponible temporalmente.")

    # Gemini API call
    gemini_start = time.time()
    gemini = GeminiService()
    agent_response, reply_meta = gemini.generate_response(full_prompt)
    timings['gemini_api'] = time.time() - gemini_start

    # Extraer datos del agente
    reply_text = agent_response.get("reply_to_user", "")
    analysis = agent_response.get("analysis", {})

    if reply_meta.get("source") == "security_guardrail":
        action = "BLOCK"
        toxicity = 4
        reply_text = "Contenido bloqueado por seguridad."
    else:
        action = analysis.get("action", "REPLY")
        toxicity = analysis.get("toxicity_level", 0)

    client_score = analysis.get("customer_score", 0)

    # Normalizar respuesta
    reply_text = normalize_chat_response(reply_text)

    # --- EJECUCIÓN DE ACCIONES DEL AGENTE ---

    # CASO 1: BLOQUEO POR TOXICIDAD
    if action == "BLOCK" or toxicity >= 3:
        security.block_user("Bloqueo por toxicidad grave (Agente IA).")

        BotConversationLog.objects.create(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=client_ip,
            message=user_message,
            response=reply_text,
            was_blocked=True,
            block_reason="agent_toxicity_block",
            latency_ms=int((time.time() - start_time) * 1000),
            response_meta=reply_meta
        )

        raise PermissionError("Este chat ha sido suspendido por incumplimiento de normas.")

    # CASO 2: HANDOFF
    handoff_data_pending = None
    if action == "HANDOFF":
        conversation_history = ConversationMemoryService.get_conversation_history(user_id_for_security)
        conversation_context = {
            'last_messages': conversation_history[-6:],
            'escalation_message': user_message,
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
        }

        if user:
            handoff_data_pending['user'] = user
        else:
            handoff_data_pending['anonymous_user'] = anonymous_user

        reply_meta['handoff_detected'] = True
        reply_meta['client_score'] = client_score

    # ÉXITO
    timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}
    reply_meta['timings'] = timings_ms
    reply_meta['agent_analysis'] = analysis

    response_payload = {
        "reply": reply_text,
        "meta": reply_meta
    }

    if anonymous_user:
        response_payload['session_id'] = str(anonymous_user.session_id)

    # Registrar conversación
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
        handoff_data_pending['conversation_log'] = conversation_log
        handoff_request = HumanHandoffRequest.objects.create(**handoff_data_pending)

        from bot.tasks import check_handoff_timeout
        check_handoff_timeout.apply_async(args=[handoff_request.id], countdown=300)

        try:
            HandoffNotificationService.send_handoff_notification(handoff_request)
        except Exception as e:
            logger.error("Error notificaciones handoff: %s", e)

        reply_meta['handoff_created'] = True
        reply_meta['handoff_id'] = handoff_request.id
        response_payload['meta'] = reply_meta

    # Guardar en historial
    ConversationMemoryService.add_to_history(user_id_for_security, user_message, reply_text)

    # Cachear respuesta
    cache.set(dedup_key, response_payload, timeout=dedup_window * 2)

    return response_payload
