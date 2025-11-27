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

from ..models import (
    AnonymousUser,
    BotConfiguration,
    BotConversationLog,
    HumanHandoffRequest,
)
from ..notifications import HandoffNotificationService
from ..security import BotSecurityService
from ..services import ConversationMemoryService, GeminiService, PromptOrchestrator
from ..suspicious_activity_detector import SuspiciousActivityDetector
from ..throttling import BotDailyThrottle, BotIPThrottle, BotRateThrottle

logger = logging.getLogger(__name__)


class BotWebhookView(APIView):
    permission_classes = [AllowAny]  # Soporte para usuarios anónimos y registrados
    # CORRECCIÓN CRÍTICA: Aplicar throttle por minuto Y diario
    # MEJORA #4: Agregar throttle por IP para prevenir abuso con múltiples cuentas
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def _get_client_ip(self, request):
        """
        BOT-SEC-FORWARDED-IP: Obtiene la IP real del cliente de forma segura.
        
        Solo confía en X-Forwarded-For si:
        1. TRUST_PROXY está habilitado en settings
        2. La petición proviene de un proxy autorizado
        
        Esto previene que clientes maliciosos falsifiquen su IP para evadir
        bloqueos, throttles y límites diarios.
        """
        import ipaddress
        from django.conf import settings
        
        # IP directa del request (siempre confiable)
        remote_addr = request.META.get('REMOTE_ADDR', '127.0.0.1')
        
        # Verificar si debemos confiar en proxies
        trust_proxy = getattr(settings, 'TRUST_PROXY', False)
        
        if not trust_proxy:
            # No confiar en X-Forwarded-For, usar IP directa
            try:
                ipaddress.ip_address(remote_addr)
                return remote_addr
            except (ValueError, TypeError):
                logger.warning("IP inválida recibida: %s. Usando IP por defecto.", remote_addr)
                return '0.0.0.0'
        
        # Si confiamos en proxies, procesar X-Forwarded-For
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        
        if x_forwarded_for:
            # X-Forwarded-For puede contener múltiples IPs: "client, proxy1, proxy2"
            # Tomamos la primera IP (la del cliente original)
            ips = [ip.strip() for ip in x_forwarded_for.split(',')]
            client_ip = ips[0] if ips else remote_addr
            
            # Validar formato de IP
            try:
                ipaddress.ip_address(client_ip)
                
                # Registrar en logs para auditoría
                if len(ips) > 1:
                    logger.debug(
                        "X-Forwarded-For chain: %s, using client IP: %s",
                        x_forwarded_for, client_ip
                    )
                
                return client_ip
            except (ValueError, TypeError):
                logger.warning(
                    "IP inválida en X-Forwarded-For: %s. Usando REMOTE_ADDR: %s",
                    client_ip, remote_addr
                )
                return remote_addr
        else:
            # No hay X-Forwarded-For, usar IP directa
            try:
                ipaddress.ip_address(remote_addr)
                return remote_addr
            except (ValueError, TypeError):
                logger.warning("IP inválida recibida: %s. Usando IP por defecto.", remote_addr)
                return '0.0.0.0'

    def _get_or_create_anonymous_user(self, request):
        """
        Obtiene o crea un usuario anónimo basado en session_id o crea uno nuevo.
        Retorna una tupla (anonymous_user, user_id_for_security)
        """
        # Intentar obtener session_id del request (header o body)
        session_id = request.data.get('session_id') or request.headers.get('X-Session-ID')

        ip_address = self._get_client_ip(request)

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

    def _normalize_chat_response(self, text: str) -> str:
        """
        Normaliza la respuesta para formato de chat con píldoras.
        - Convierte \\n\\n a \\n (un solo salto)
        - Asegura espacio después de cada \\n
        - Divide párrafos largos en fragmentos más cortos
        """
        import re
        
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
        client_ip = self._get_client_ip(request)
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
        reply_text = self._normalize_chat_response(reply_text)

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


class BotHealthCheckView(APIView):
    """
    BOT-HEALTH-PARTIAL: Health check mejorado que verifica dependencias reales.
    
    Verifica:
    - Cache (Redis)
    - Base de datos
    - Gemini API configuration
    - Configuración activa del bot
    - Celery workers (opcional con ?check_celery=1)
    
    Retorna 200 si todo está OK, 503 si alguna dependencia crítica falla.
    """
    permission_classes = []  # Público para load balancers

    def get(self, request):
        # Verificar si se solicita detalle (solo para staff)
        show_details = request.query_params.get('details') == '1' and (
            request.user.is_authenticated and request.user.is_staff
        )
        
        checks = {
            'cache': self._check_cache(),
            'database': self._check_database(),
            'gemini_api': self._check_gemini(),
            'configuration': self._check_config(),
        }
        
        # Verificar Celery solo si se solicita explícitamente
        if request.query_params.get('check_celery') == '1':
            checks['celery'] = self._check_celery()
        
        # Determinar salud general (cache, db y config son críticos)
        critical_checks = [checks['cache'], checks['database'], checks['configuration']]
        all_healthy = all(critical_checks)
        
        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        # Respuesta básica para load balancers
        response_data = {
            'status': 'healthy' if all_healthy else 'unhealthy',
            'service': 'bot',
        }
        
        # Si se solicitan detalles y el usuario es staff, incluir componentes
        if show_details:
            response_data['components'] = checks
        
        return Response(response_data, status=status_code)
    
    def _check_cache(self) -> bool:
        """Verifica que Redis/cache esté funcionando"""
        try:
            test_key = 'bot_health_check_test'
            cache.set(test_key, 'ok', 10)
            result = cache.get(test_key)
            cache.delete(test_key)
            return result == 'ok'
        except Exception as e:
            logger.error("Health check cache failed: %s", e)
            return False
    
    def _check_database(self) -> bool:
        """Verifica que la base de datos esté funcionando"""
        try:
            from django.db import connections
            cursor = connections['default'].cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Exception as e:
            logger.error("Health check database failed: %s", e)
            return False
    
    def _check_gemini(self) -> bool:
        """
        Verifica que la API key de Gemini esté configurada Y que el SDK esté instalado.
        """
        try:
            import os
            from django.conf import settings
            
            # 1. Verificar API Key
            api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                return False
                
            # 2. Verificar instalación del SDK
            try:
                from google import genai
                # 3. Verificar instanciación básica (sin llamada de red)
                client = genai.Client(api_key=api_key)
                return True
            except ImportError:
                logger.error("Health check Gemini failed: google-genai not installed")
                return False
            except Exception as e:
                logger.error("Health check Gemini failed during init: %s", e)
                return False
                
        except Exception as e:
            logger.error("Health check Gemini failed: %s", e)
            return False
    
    def _check_config(self) -> bool:
        """Verifica que exista una configuración activa"""
        try:
            config = BotConfiguration.objects.filter(is_active=True).first()
            return config is not None
        except Exception as e:
            logger.error("Health check config failed: %s", e)
            return False
    
    def _check_celery(self) -> bool:
        """
        Verifica que haya workers de Celery activos.
        Solo se ejecuta si se solicita explícitamente.
        """
        try:
            from celery.app.control import Inspect
            from studiozens.celery import app as celery_app
            
            inspector = Inspect(app=celery_app)
            # Timeout de 2 segundos para no bloquear el health check
            active_workers = inspector.ping(timeout=2.0)
            return bool(active_workers)
        except Exception as e:
            logger.error("Health check Celery failed: %s", e)
            return False


class WhatsAppWebhookView(APIView):
    """
    Webhook para recibir mensajes entrantes de Twilio WhatsApp.

    POST /api/v1/bot/whatsapp/
    Content-Type: application/x-www-form-urlencoded

    Twilio envía:
    - Body: Texto del mensaje
    - From: Número de teléfono del remitente (whatsapp:+573001234567)
    - To: Número de tu negocio
    - MessageSid: ID del mensaje
    - X-Twilio-Signature: Firma para validación (opcional)

    Responde con TwiML:
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>Respuesta del bot</Message>
    </Response>
    """
    permission_classes = [AllowAny]
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def _get_client_ip(self, request):
        """Obtiene la IP real del cliente (reutilizado de BotWebhookView)"""
        import ipaddress

        remote_addr = request.META.get('REMOTE_ADDR', '127.0.0.1')
        trust_proxy = getattr(settings, 'TRUST_PROXY', False)

        if not trust_proxy:
            try:
                ipaddress.ip_address(remote_addr)
                return remote_addr
            except (ValueError, TypeError):
                logger.warning("IP inválida: %s", remote_addr)
                return '0.0.0.0'

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ips = [ip.strip() for ip in x_forwarded_for.split(',')]
            client_ip = ips[0] if ips else remote_addr

            try:
                ipaddress.ip_address(client_ip)
                return client_ip
            except (ValueError, TypeError):
                logger.warning("IP inválida en X-Forwarded-For: %s", client_ip)
                return remote_addr
        else:
            try:
                ipaddress.ip_address(remote_addr)
                return remote_addr
            except (ValueError, TypeError):
                return '0.0.0.0'

    def _validate_twilio_signature(self, request):
        """
        Valida la firma de Twilio para asegurar que el request viene de Twilio.
        Opcional pero recomendado para producción.

        Returns:
            bool: True si la firma es válida o si la validación está desactivada
        """
        # Solo validar si está configurado
        if not getattr(settings, 'VALIDATE_TWILIO_SIGNATURE', False):
            return True

        try:
            from twilio.request_validator import RequestValidator

            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            if not auth_token:
                logger.warning("TWILIO_AUTH_TOKEN no configurado, saltando validación de firma")
                return True

            validator = RequestValidator(auth_token)

            # Obtener URL completa del request
            url = request.build_absolute_uri()

            # Obtener firma del header
            signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

            # Obtener parámetros POST
            params = request.POST.dict()

            # Validar
            is_valid = validator.validate(url, params, signature)

            if not is_valid:
                logger.warning("Firma de Twilio inválida. URL: %s", url)

            return is_valid

        except ImportError:
            logger.warning("twilio package no instalado, saltando validación de firma")
            return True
        except Exception as e:
            logger.error("Error validando firma de Twilio: %s", e)
            return False

    def _normalize_phone_number(self, whatsapp_number: str) -> str:
        """
        Normaliza número de WhatsApp a formato E.164.

        Input: whatsapp:+573001234567
        Output: +573001234567
        """
        if whatsapp_number.startswith('whatsapp:'):
            return whatsapp_number[9:]  # Remover prefijo 'whatsapp:'
        return whatsapp_number

    def _get_user_from_phone(self, phone_number: str):
        """
        Busca usuario por número de teléfono.

        Returns:
            tuple: (user, anonymous_user, user_id_for_security)
        """
        from users.models import CustomUser

        # Intentar encontrar usuario registrado
        user = CustomUser.objects.filter(
            phone_number=phone_number,
            is_active=True
        ).first()

        if user:
            return user, None, str(user.id)

        # Usuario no registrado, crear anónimo temporal
        # Usamos el número de teléfono como identificador único
        client_ip = '0.0.0.0'  # Twilio no pasa IP del cliente

        # Buscar si ya existe un usuario anónimo con este teléfono en metadata
        anonymous_user = AnonymousUser.objects.filter(
            metadata__phone_number=phone_number
        ).first()

        if not anonymous_user or anonymous_user.is_expired:
            # Crear nuevo usuario anónimo
            anonymous_user = AnonymousUser.objects.create(
                ip_address=client_ip,
                metadata={'phone_number': phone_number, 'channel': 'whatsapp'}
            )
            logger.info("Nuevo usuario anónimo WhatsApp creado: %s", phone_number)

        return None, anonymous_user, f"whatsapp_{phone_number}"

    def _get_last_notification(self, user, phone_number: str):
        """
        Obtiene la última notificación enviada al usuario por WhatsApp.

        Returns:
            dict o None
        """
        from notifications.models import NotificationLog, NotificationTemplate

        # Buscar última notificación
        if user:
            last_log = NotificationLog.objects.filter(
                user=user,
                channel=NotificationTemplate.ChannelChoices.WHATSAPP,
                status=NotificationLog.Status.SENT
            ).order_by('-created_at').first()
        else:
            # Para usuarios anónimos, buscar por teléfono en metadata
            last_log = NotificationLog.objects.filter(
                metadata__phone_number=phone_number,
                channel=NotificationTemplate.ChannelChoices.WHATSAPP,
                status=NotificationLog.Status.SENT
            ).order_by('-created_at').first()

        if not last_log:
            return None

        # Construir diccionario con info relevante
        payload = last_log.payload or {}
        return {
            'event_code': last_log.event_code,
            'subject': payload.get('subject', ''),
            'body': payload.get('body', ''),
            'sent_at': last_log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'channel': 'WhatsApp',
            'metadata': last_log.metadata or {}
        }

    def _generate_twiml_response(self, message_text: str) -> str:
        """
        Genera respuesta en formato TwiML para Twilio.

        Args:
            message_text: Texto de la respuesta del bot

        Returns:
            str: XML TwiML
        """
        # Escapar caracteres especiales XML
        import html
        escaped_text = html.escape(message_text)

        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{escaped_text}</Message>
</Response>'''

        return twiml

    def post(self, request):
        """
        Procesa mensaje entrante de WhatsApp vía Twilio.
        """
        # 1. Validar firma de Twilio (opcional pero recomendado)
        if not self._validate_twilio_signature(request):
            logger.warning("Firma de Twilio inválida rechazada")
            return Response(
                self._generate_twiml_response("Error de autenticación."),
                content_type='application/xml',
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Extraer datos del formulario de Twilio
        try:
            body = request.POST.get('Body', '').strip()
            from_number = request.POST.get('From', '')
            message_sid = request.POST.get('MessageSid', '')

            logger.info("WhatsApp webhook recibido. From: %s, MessageSid: %s", from_number, message_sid)

            # 3. Validar que tengamos mensaje
            if not body:
                return Response(
                    self._generate_twiml_response("No recibí ningún mensaje. ¿Puedes escribir algo?"),
                    content_type='application/xml'
                )

            # 4. Normalizar número de teléfono
            phone_number = self._normalize_phone_number(from_number)

            # 5. Obtener o crear usuario
            user, anonymous_user, user_id_for_security = self._get_user_from_phone(phone_number)

            # 6. Obtener última notificación (contexto adicional)
            last_notification = self._get_last_notification(user, phone_number)
            extra_context = None
            if last_notification:
                extra_context = {"last_notification": last_notification}

            # 7. Obtener IP del cliente
            client_ip = self._get_client_ip(request)

            # 8. Procesar mensaje con la lógica compartida
            from ..services_shared import process_bot_message

            response_data = process_bot_message(
                user=user,
                anonymous_user=anonymous_user,
                user_message=body,
                client_ip=client_ip,
                user_id_for_security=user_id_for_security,
                extra_context=extra_context
            )

            reply_text = response_data.get('reply', 'Lo siento, hubo un error procesando tu mensaje.')

            logger.info(
                "WhatsApp respuesta enviada. To: %s, MessageSid: %s",
                phone_number, message_sid
            )

        except PermissionError as e:
            # Usuario bloqueado o límite excedido
            reply_text = str(e)
            logger.warning("WhatsApp mensaje bloqueado: %s", e)

        except ValueError as e:
            # Error de validación
            reply_text = f"Error: {str(e)}"
            logger.warning("WhatsApp validación fallida: %s", e)

        except RuntimeError as e:
            # Error del sistema
            reply_text = "El servicio está temporalmente no disponible. Por favor intenta más tarde."
            logger.error("WhatsApp error del sistema: %s", e)

        except Exception as e:
            # Error inesperado
            reply_text = "Ocurrió un error inesperado. Por favor intenta de nuevo."
            logger.exception("WhatsApp error inesperado: %s", e)

        # 9. Generar y devolver TwiML
        twiml_response = self._generate_twiml_response(reply_text)

        return Response(
            twiml_response,
            content_type='application/xml',
            status=status.HTTP_200_OK
        )

