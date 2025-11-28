"""
Vista principal del webhook del bot para mensajes web.
"""
import hashlib
import logging
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ...models import (
    AnonymousUser,
    BotConversationLog,
    HumanHandoffRequest,
)
from ...notifications import HandoffNotificationService
from ...security import BotSecurityService
from ...services import ConversationMemoryService, GeminiService, PromptOrchestrator
from ...suspicious_activity_detector import SuspiciousActivityDetector
from ...throttling import BotDailyThrottle, BotIPThrottle, BotRateThrottle
from .utils import get_client_ip, normalize_chat_response

logger = logging.getLogger(__name__)


class BotWebhookView(APIView):
    permission_classes = [AllowAny]  # Soporte para usuarios anónimos y registrados
    # CORRECCIÓN CRÍTICA: Aplicar throttle por minuto Y diario
    # MEJORA #4: Agregar throttle por IP para prevenir abuso con múltiples cuentas
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def _get_or_create_anonymous_user(self, request):
        """
        Obtiene o crea un usuario anónimo basado en session_id o crea uno nuevo.
        Retorna una tupla (anonymous_user, user_id_for_security)
        """
        # Intentar obtener session_id del request (header o body)
        session_id = request.data.get('session_id') or request.headers.get('X-Session-ID')

        ip_address = get_client_ip(request)

        if session_id:
            try:
                # Validar que sea un UUID válido
                session_uuid = uuid.UUID(session_id)
                # Buscar usuario anónimo existente
                anon_user = AnonymousUser.objects.filter(session_id=session_uuid).first()

                if anon_user:
                    # Verificar si no está expirado
                    if not anon_user.is_expired:
                        # CORRECCIÓN SEGURIDAD: Validar que la IP coincida (prevenir session hijacking)
                        if anon_user.ip_address != ip_address:
                            logger.warning(
                                "Intento de reutilizar session_id %s desde IP diferente. "
                                "Original: %s, Actual: %s. Creando nueva sesión.",
                                session_id, anon_user.ip_address, ip_address
                            )
                            # No reusar la sesión, crear nueva
                        else:
                            # IP coincide, actualizar last_activity (se hace automáticamente con auto_now)
                            anon_user.save()
                            # Usar el PK del usuario anónimo como ID para seguridad
                            return anon_user, f"anon_{anon_user.pk}"
                    else:
                        # Sesión expirada, crear nueva
                        logger.info("Sesión anónima expirada: %s", session_id)
            except (ValueError, TypeError):
                # UUID inválido, crear nuevo
                logger.warning("Session ID inválido recibido: %s", session_id)

        # Crear nuevo usuario anónimo
        anon_user = AnonymousUser.objects.create(
            ip_address=ip_address
        )
        logger.info("Nuevo usuario anónimo creado: %s desde IP %s", anon_user.session_id, ip_address)

        return anon_user, f"anon_{anon_user.pk}"

    def post(self, request):
        # CORRECCIÓN SEGURIDAD: Primero validar el mensaje antes de crear objetos en BD

        # 1. Validar tipo de dato del mensaje (Evitar AttributeError en .strip())
        raw_message = request.data.get("message")
        if raw_message is not None and not isinstance(raw_message, str):
            return Response(
                {"error": "Formato inválido. El mensaje debe ser texto."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_message = (raw_message or "").strip()

        if not user_message:
            return Response(
                {"error": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Determinar si es usuario autenticado o anónimo
        # CORRECCIÓN SEGURIDAD: Solo crear AnonymousUser después de validaciones básicas
        if request.user.is_authenticated:
            user = request.user
            anonymous_user = None
            user_id_for_security = user.id
        else:
            user = None
            anonymous_user, user_id_for_security = self._get_or_create_anonymous_user(request)

        security = BotSecurityService(user_id_for_security)

        # CORRECCIÓN CRÍTICA: Tracking de latencia para auditoría
        start_time = time.time()

        # MEJORA #12: Tracking de tiempos por componente
        timings = {}

        # ---------------------------------------------------------
        # NIVEL 1: BLOQUEOS PREVIOS (Costo computacional: Muy bajo)
        # ---------------------------------------------------------
        security_start = time.time()

        # 0. CHEQUEO DE IP BLOQUEADA (Prioridad máxima)
        client_ip = get_client_ip(request)
        ip_blocked, ip_block_reason = SuspiciousActivityDetector.check_ip_blocked(client_ip)
        if ip_blocked:
            return Response(
                {"reply": ip_block_reason, "meta": {"blocked": True, "reason": "ip_blocked"}},
                status=status.HTTP_403_FORBIDDEN
            )

        # 1. ¿Está el usuario castigado actualmente?
        is_blocked, reason = security.is_blocked()
        if is_blocked:
            return Response(
                {"reply": reason, "meta": {"blocked": True}},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Validación de longitud (Payload size)
        valid_len, len_error = security.validate_input_length(user_message)
        if not valid_len:
            return Response(
                {"error": len_error},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2.5 CORRECCIÓN CRÍTICA: Validación de contenido (Jailbreak detection)
        valid_content, content_error = security.validate_input_content(user_message)
        if not valid_content:
            # Registrar intento de jailbreak
            SuspiciousActivityDetector.detect_jailbreak_attempt(
                user, anonymous_user, client_ip, user_message
            )
            return Response(
                {"error": content_error},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2.6 LÍMITE DIARIO: Verificar que no exceda límites (30 por usuario, 50 por IP)
        exceeded_daily, daily_error = security.check_daily_limit(ip_address=client_ip)
        if exceeded_daily:
            # Registrar abuso de límite diario
            # Extraer el conteo actual del mensaje de error si es posible
            import re
            match = re.search(r'(\d+)/(\d+)', daily_error)
            current_count = int(match.group(1)) if match else 50
            limit = int(match.group(2)) if match else 50

            SuspiciousActivityDetector.detect_daily_limit_abuse(
                user, anonymous_user, client_ip, current_count, limit
            )
            return Response(
                {"reply": daily_error, "meta": {"blocked": True, "reason": "daily_limit"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # ---------------------------------------------------------
        # CORRECCIÓN CRÍTICA: DEDUPLICACIÓN DE REQUESTS
        # Evita que requests duplicados (retry, doble clic) consuman tokens
        # y causen bloqueos incorrectos
        # ---------------------------------------------------------
        dedup_window = 10  # segundos - ventana de deduplicación
        dedup_id = hashlib.sha256(
            f"{user_id_for_security}:{user_message}:{int(time.time() / dedup_window)}".encode()
        ).hexdigest()[:16]
        dedup_key = f"bot:dedup:{dedup_id}"

        # Verificar si ya procesamos este mensaje recientemente
        cached_response = cache.get(dedup_key)
        if cached_response:
            logger.info(
                "Request duplicado detectado para user_id %s. Devolviendo respuesta cacheada.",
                user_id_for_security
            )
            return Response(cached_response)

        # 3. CHEQUEO DE VELOCIDAD (Protección de Billetera)
        # Si envía muchos mensajes en < 60s, se bloquea por script/bot malicioso.
        # MEJORA #16: Retry logic para casos de contención de cache
        MAX_RETRIES = 2

        for attempt in range(MAX_RETRIES + 1):
            try:
                if security.check_velocity():
                    # Registrar abuso de límite de velocidad
                    SuspiciousActivityDetector.detect_rate_limit_abuse(
                        user, anonymous_user, client_ip
                    )
                    return Response(
                        {"reply": "Estás enviando mensajes demasiado rápido. Acceso pausado por 24h.", "meta": {
                            "blocked": True}},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )

                # 4. CHEQUEO DE REPETICIÓN (Fuzzy Matching)
                # Si el mensaje es muy similar a los anteriores.
                if security.check_repetition(user_message):
                    # Registrar mensajes repetitivos
                    SuspiciousActivityDetector.detect_repetitive_messages(
                        user, anonymous_user, client_ip, user_message
                    )
                    return Response(
                        {"reply": "Hemos detectado mensajes repetitivos. Acceso pausado por 24h.", "meta": {
                            "blocked": True}},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )

                # Éxito, salir del loop
                break

            except BlockingIOError:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Lock contention para usuario %s, reintentando (%d/%d)",
                        user_id_for_security, attempt + 1, MAX_RETRIES
                    )
                    time.sleep(0.1 * (attempt + 1))  # Backoff exponencial: 0.1s, 0.2s
                    continue
                else:
                    # Último intento falló
                    logger.error(
                        "Lock contention persistente para usuario %s después de %d intentos",
                        user_id_for_security, MAX_RETRIES
                    )
                    return Response(
                        {"error": "El sistema está experimentando alta carga. Intenta en unos segundos."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )

        timings['security_checks'] = time.time() - security_start

        # ---------------------------------------------------------
        # MODO ASÍNCRONO (BOT-ASYNC-QUEUE)
        # ---------------------------------------------------------
        if getattr(settings, 'BOT_ASYNC_MODE', False):
            # Encolar tarea en Celery
            from bot.tasks import process_bot_message_async

            # ID para deduplicación (usamos el mismo dedup_id generado antes)
            dedup_key_id = dedup_id

            task = process_bot_message_async.delay(
                user_id=user.id if user else None,
                anonymous_user_id=anonymous_user.id if anonymous_user else None,
                message=user_message,
                client_ip=client_ip,
                conversation_history=None, # La tarea lo obtendrá de cache/DB
                dedup_id=dedup_key_id
            )

            logger.info(
                "Mensaje encolado async. Task: %s | User: %s",
                task.id, user_id_for_security
            )

            return Response({
                'status': 'queued',
                'task_id': task.id,
                'message': 'Tu mensaje está siendo procesado...',
                'meta': {
                    'queued': True,
                    'timings': timings
                }
            }, status=status.HTTP_202_ACCEPTED)

        # ---------------------------------------------------------
        # NIVEL 2: INTELIGENCIA ARTIFICIAL (Costo: Tokens / Latencia)
        # ---------------------------------------------------------

        # Prompt building
        prompt_start = time.time()
        orchestrator = PromptOrchestrator()
        full_prompt, is_valid = orchestrator.build_full_prompt(
            user, user_message, user_id_for_memory=user_id_for_security
        )
        timings['prompt_building'] = time.time() - prompt_start

        if not is_valid:
            return Response(
                {
                    "error": "El servicio de chat no está disponible temporalmente. "
                             "Por favor intenta más tarde."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # Gemini API call (Agentic JSON Mode)
        gemini_start = time.time()
        gemini = GeminiService()

        # response_data es un DICT (JSON parseado), meta es DICT
        agent_response, reply_meta = gemini.generate_response(full_prompt)
        timings['gemini_api'] = time.time() - gemini_start

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
                user=user, anonymous_user=anonymous_user, ip_address=client_ip,
                message=user_message, response=reply_text,
                was_blocked=True, block_reason="agent_toxicity_block",
                latency_ms=int((time.time() - start_time) * 1000),
                response_meta=reply_meta
            )

            return Response({
                "reply": "Este chat ha sido suspendido por incumplimiento de normas.",
                "meta": {"blocked": True, "reason": "toxicity"}
            }, status=status.HTTP_403_FORBIDDEN)

        # CASO 2: HANDOFF (Escalamiento a Humano)
        handoff_data_pending = None
        if action == "HANDOFF":
            # El agente ya verificó que tiene servicio y contacto (si aplica)

            # Contexto para el humano
            conversation_history = ConversationMemoryService.get_conversation_history(user_id_for_security)
            conversation_context = {
                'last_messages': conversation_history[-6:],
                'escalation_message': user_message,
                'bot_response': reply_text,
                'toxicity_level': toxicity,
                'missing_info': analysis.get("missing_info")
            }

            # Intereses (simplificado, el agente ya hizo el scoring)
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

        # ÉXITO: Mensaje válido y procesado.
        timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}
        reply_meta['timings'] = timings_ms
        reply_meta['agent_analysis'] = analysis # Guardar análisis completo para debugging

        response_payload = {
            "reply": reply_text,
            "meta": reply_meta
        }

        if anonymous_user:
            response_payload['session_id'] = str(anonymous_user.session_id)

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
            handoff_data_pending['conversation_log'] = conversation_log
            handoff_request = HumanHandoffRequest.objects.create(**handoff_data_pending)

            # Programar timeout de 5 minutos
            from bot.tasks import check_handoff_timeout
            check_handoff_timeout.apply_async(args=[handoff_request.id], countdown=300)

            # Notificar
            try:
                HandoffNotificationService.send_handoff_notification(handoff_request)
            except Exception as e:
                logger.error("Error notificaciones handoff: %s", e)

            reply_meta['handoff_created'] = True
            reply_meta['handoff_id'] = handoff_request.id
            response_payload['meta'] = reply_meta

        # Guardar en historial
        ConversationMemoryService.add_to_history(user_id_for_security, user_message, reply_text)

        # Cachear respuesta para deduplicación
        cache.set(dedup_key, response_payload, timeout=dedup_window * 2)

        return Response(response_payload)
