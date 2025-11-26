import hashlib
import logging
import time
import uuid

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    PromptOrchestrator, GeminiService, ConversationMemoryService
)
from .security import BotSecurityService
from .throttling import BotRateThrottle, BotDailyThrottle, BotIPThrottle
from .models import (
    BotConversationLog, BotConfiguration, AnonymousUser,
    HumanHandoffRequest, HumanMessage, SuspiciousActivity, IPBlocklist
)
from .notifications import HandoffNotificationService
from .suspicious_activity_detector import SuspiciousActivityDetector, SuspiciousActivityAnalyzer
from .serializers import (
    HumanHandoffRequestListSerializer, HumanHandoffRequestDetailSerializer,
    HumanHandoffRequestUpdateSerializer, HumanMessageSerializer,
    HumanMessageCreateSerializer, HandoffAssignSerializer, HandoffResolveSerializer
)

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
            from zenzspa.celery import app as celery_app
            
            inspector = Inspect(app=celery_app)
            # Timeout de 2 segundos para no bloquear el health check
            active_workers = inspector.ping(timeout=2.0)
            return bool(active_workers)
        except Exception as e:
            logger.error("Health check Celery failed: %s", e)
            return False



class HumanHandoffRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar solicitudes de handoff humano.

    Endpoints:
    - GET /handoffs/ - Listar handoffs (filtros: status, assigned_to_me)
    - GET /handoffs/{id}/ - Ver detalle de handoff
    - PATCH /handoffs/{id}/ - Actualizar handoff (status, notas)
    - POST /handoffs/{id}/assign/ - Asignarse el handoff
    - POST /handoffs/{id}/resolve/ - Marcar como resuelto
    - GET /handoffs/{id}/messages/ - Ver mensajes
    - POST /handoffs/{id}/messages/ - Enviar mensaje
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filtrar handoffs según rol:
        - STAFF y ADMIN ven todos
        - Usuarios normales no tienen acceso
        """
        from users.models import CustomUser

        user = self.request.user

        # Solo STAFF y ADMIN pueden ver handoffs
        if not (user.is_superuser or user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]):
            return HumanHandoffRequest.objects.none()

        queryset = HumanHandoffRequest.objects.all().select_related(
            'user', 'anonymous_user', 'assigned_to', 'conversation_log'
        ).prefetch_related('messages')

        # Filtros opcionales
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filtro "assigned_to_me"
        assigned_to_me = self.request.query_params.get('assigned_to_me')
        if assigned_to_me and assigned_to_me.lower() in ['true', '1']:
            queryset = queryset.filter(assigned_to=user)

        # Filtro "unassigned" (pendientes sin asignar)
        unassigned = self.request.query_params.get('unassigned')
        if unassigned and unassigned.lower() in ['true', '1']:
            queryset = queryset.filter(status=HumanHandoffRequest.Status.PENDING, assigned_to__isnull=True)

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        """Usar serializer apropiado según la acción"""
        if self.action == 'list':
            return HumanHandoffRequestListSerializer
        elif self.action in ['update', 'partial_update']:
            return HumanHandoffRequestUpdateSerializer
        elif self.action == 'assign':
            return HandoffAssignSerializer
        elif self.action == 'resolve':
            return HandoffResolveSerializer
        return HumanHandoffRequestDetailSerializer

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        Asignar el handoff al usuario actual.

        POST /api/v1/bot/handoffs/{id}/assign/
        """
        handoff = self.get_object()

        # Solo permitir asignar si está PENDING
        if handoff.status != HumanHandoffRequest.Status.PENDING:
            return Response(
                {'error': 'Solo se pueden asignar handoffs en estado PENDING'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Asignar al usuario actual
        handoff.assigned_to = request.user
        handoff.status = HumanHandoffRequest.Status.ASSIGNED
        handoff.assigned_at = timezone.now()
        handoff.save()

        logger.info(
            "Handoff %d asignado a %s",
            handoff.id, request.user.get_full_name()
        )

        serializer = HumanHandoffRequestDetailSerializer(handoff)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        Marcar handoff como resuelto.

        POST /api/v1/bot/handoffs/{id}/resolve/
        Body: {"resolution_notes": "..."}
        """
        handoff = self.get_object()
        serializer = HandoffResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Solo permitir resolver si está asignado o en progreso
        if handoff.status not in [HumanHandoffRequest.Status.ASSIGNED, HumanHandoffRequest.Status.IN_PROGRESS]:
            return Response(
                {'error': 'Solo se pueden resolver handoffs asignados o en progreso'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Agregar notas de resolución si se proporcionaron
        resolution_notes = serializer.validated_data.get('resolution_notes')
        if resolution_notes:
            if handoff.internal_notes:
                handoff.internal_notes += f"\n\n--- RESOLUCIÓN ---\n{resolution_notes}"
            else:
                handoff.internal_notes = f"--- RESOLUCIÓN ---\n{resolution_notes}"

        # Marcar como resuelto
        handoff.status = HumanHandoffRequest.Status.RESOLVED
        handoff.resolved_at = timezone.now()
        handoff.save()

        logger.info(
            "Handoff %d marcado como resuelto por %s",
            handoff.id, request.user.get_full_name()
        )

        serializer = HumanHandoffRequestDetailSerializer(handoff)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """
        Listar mensajes del handoff.

        GET /api/v1/bot/handoffs/{id}/messages/
        """
        handoff = self.get_object()
        messages = handoff.messages.all().order_by('created_at')

        # Marcar mensajes del cliente como leídos
        unread_client_messages = messages.filter(is_from_staff=False, read_at__isnull=True)
        for msg in unread_client_messages:
            msg.mark_as_read()

        serializer = HumanMessageSerializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='messages/send')
    def send_message(self, request, pk=None):
        """
        BOT-SEC-HUMAN-CHAT: Enviar mensaje al cliente con validación de ownership.

        POST /api/v1/bot/handoffs/{id}/messages/send/
        Body: {"message": "..."}
        
        Validaciones:
        - Solo el staff asignado o admins pueden responder
        - Se notifica al cliente por email
        - Se registra delivery tracking
        """
        handoff = self.get_object()
        
        # VALIDACIÓN DE OWNERSHIP: Solo el asignado o admins pueden responder
        if handoff.assigned_to and handoff.assigned_to != request.user:
            # Verificar si es admin/superuser
            if not request.user.is_superuser:
                return Response(
                    {
                        'error': 'Solo el staff asignado o administradores pueden responder este handoff',
                        'assigned_to': handoff.assigned_to.get_full_name() if handoff.assigned_to else None
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # Crear el mensaje
        data = {
            'handoff_request': handoff.id,
            'message': request.data.get('message'),
            'attachments': request.data.get('attachments', [])
        }

        serializer = HumanMessageCreateSerializer(
            data=data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        # Si el handoff estaba ASSIGNED, moverlo a IN_PROGRESS
        if handoff.status == HumanHandoffRequest.Status.ASSIGNED:
            handoff.status = HumanHandoffRequest.Status.IN_PROGRESS
            handoff.save()

        logger.info(
            "Mensaje enviado en handoff %d por %s",
            handoff.id, request.user.get_full_name()
        )

        # NOTIFICACIÓN AL CLIENTE: Enviar email/SMS
        try:
            self._send_client_notification(handoff, message)
        except Exception as e:
            # No fallar el request si la notificación falla
            logger.error(
                "Error enviando notificación al cliente para handoff %d: %s",
                handoff.id, e
            )

        response_serializer = HumanMessageSerializer(message)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def _send_client_notification(self, handoff, message):
        """
        Envía notificación al cliente cuando staff responde.
        
        Args:
            handoff: HumanHandoffRequest instance
            message: HumanMessage instance
        """
        from django.core.mail import send_mail
        from django.conf import settings
        
        # Determinar destinatario
        if handoff.user:
            recipient_email = handoff.user.email
            recipient_name = handoff.user.get_full_name()
        elif handoff.anonymous_user:
            # Para usuarios anónimos, no tenemos email
            # TODO: Implementar notificación por SMS si tenemos teléfono
            logger.info(
                "Handoff %d es de usuario anónimo, no se puede enviar email",
                handoff.id
            )
            return
        else:
            logger.warning("Handoff %d sin usuario asociado", handoff.id)
            return
        
        if not recipient_email:
            logger.warning(
                "Usuario %s no tiene email configurado, no se puede notificar",
                recipient_name
            )
            return
        
        # Preparar email
        subject = f"Respuesta de {settings.SITE_NAME if hasattr(settings, 'SITE_NAME') else 'ZenzSpa'} - Solicitud #{handoff.id}"
        
        staff_name = message.sender.get_full_name() if message.sender else "Nuestro equipo"
        
        email_body = f"""
Hola {recipient_name},

{staff_name} ha respondido a tu solicitud:

"{message.message}"

Puedes continuar la conversación respondiendo a este email o visitando tu cuenta.

Saludos,
El equipo de ZenzSpa
        """.strip()
        
        # Enviar email
        send_mail(
            subject=subject,
            message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        
        # Registrar delivery
        message.delivered_at = timezone.now()
        message.delivery_channel = 'email'
        message.save(update_fields=['delivered_at', 'delivery_channel'])
        
        logger.info(
            "Notificación enviada a %s (%s) para handoff %d",
            recipient_name, recipient_email, handoff.id
        )



class BotAnalyticsView(APIView):
    """
    Endpoint para análisis de uso y detección de fraude.
    Solo accesible para ADMIN.
    
    GET /api/v1/bot/analytics/?days=7
    
    Retorna estadísticas de uso por IP, incluyendo:
    - Top IPs por volumen de mensajes
    - IPs sospechosas (>40 mensajes/día promedio)
    - Consumo total de tokens
    - Métricas generales
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        from datetime import timedelta
        from django.db.models import Count, Sum, Avg, Q
        
        # Parámetros
        days = int(request.query_params.get('days', 7))
        since = timezone.now() - timedelta(days=days)
        
        # Estadísticas por IP
        ip_stats = BotConversationLog.objects.filter(
            created_at__gte=since,
            ip_address__isnull=False
        ).values('ip_address').annotate(
            total_messages=Count('id'),
            total_tokens=Sum('tokens_used'),
            blocked_count=Count('id', filter=Q(was_blocked=True)),
            avg_tokens_per_msg=Avg('tokens_used'),
            avg_latency_ms=Avg('latency_ms')
        ).order_by('-total_messages')
        
        # IPs sospechosas (>40 mensajes/día en promedio)
        suspicious_threshold = 40 * days
        suspicious_ips = []
        
        for ip in ip_stats:
            avg_per_day = ip['total_messages'] / days
            ip['avg_messages_per_day'] = round(avg_per_day, 1)
            
            if ip['total_messages'] > suspicious_threshold:
                suspicious_ips.append({
                    'ip_address': ip['ip_address'],
                    'total_messages': ip['total_messages'],
                    'avg_per_day': round(avg_per_day, 1),
                    'total_tokens': ip['total_tokens'],
                    'blocked_count': ip['blocked_count']
                })
        
        # Estadísticas generales
        total_stats = BotConversationLog.objects.filter(
            created_at__gte=since
        ).aggregate(
            total_conversations=Count('id'),
            total_tokens=Sum('tokens_used'),
            total_blocked=Count('id', filter=Q(was_blocked=True)),
            avg_latency=Avg('latency_ms')
        )
        
        # Conteo de IPs únicas
        unique_ips = BotConversationLog.objects.filter(
            created_at__gte=since,
            ip_address__isnull=False
        ).values('ip_address').distinct().count()
        
        return Response({
            'period_days': days,
            'since': since.isoformat(),
            'summary': {
                'total_conversations': total_stats['total_conversations'] or 0,
                'total_tokens_consumed': total_stats['total_tokens'] or 0,
                'total_blocked': total_stats['total_blocked'] or 0,
                'avg_latency_ms': round(total_stats['avg_latency'] or 0, 2),
                'unique_ips': unique_ips,
            },
            'top_ips': list(ip_stats[:20]),
            'suspicious_ips': suspicious_ips,
            'suspicious_count': len(suspicious_ips),
        })


class SuspiciousUsersView(APIView):
    """
    Endpoint para obtener usuarios/IPs sospechosos con actividad problemática.
    Solo accesible para ADMIN.

    GET /api/v1/bot/suspicious-users/?days=7&min_severity=2

    Retorna:
    - Lista de IPs con actividad sospechosa
    - Análisis de patrones de cada IP
    - Historial de actividades recientes
    - Estado de bloqueo
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Parámetros
        days = int(request.query_params.get('days', 7))
        min_severity = int(request.query_params.get('min_severity', SuspiciousActivity.SeverityLevel.MEDIUM))

        # Obtener resumen de usuarios sospechosos
        suspicious_users = SuspiciousActivityAnalyzer.get_suspicious_users_summary(
            days=days,
            min_severity=min_severity
        )

        return Response({
            'period_days': days,
            'min_severity': min_severity,
            'total_suspicious_ips': len(suspicious_users),
            'suspicious_users': suspicious_users
        })


class UserActivityTimelineView(APIView):
    """
    Endpoint para obtener el historial completo de actividad de un usuario/IP.
    Solo accesible para ADMIN.

    GET /api/v1/bot/activity-timeline/?ip=192.168.1.1&days=30
    GET /api/v1/bot/activity-timeline/?user_id=123&days=30
    GET /api/v1/bot/activity-timeline/?anon_user_id=456&days=30

    Retorna:
    - Timeline combinado de conversaciones y actividades sospechosas
    - Estadísticas del período
    - Análisis de patrones
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Parámetros
        ip_address = request.query_params.get('ip')
        user_id = request.query_params.get('user_id')
        anon_user_id = request.query_params.get('anon_user_id')
        days = int(request.query_params.get('days', 30))

        # Validar que al menos uno esté presente
        if not any([ip_address, user_id, anon_user_id]):
            return Response(
                {'error': 'Debe proporcionar al menos uno: ip, user_id, o anon_user_id'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener objetos si es necesario
        from users.models import CustomUser

        user = None
        anonymous_user = None

        if user_id:
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        if anon_user_id:
            try:
                anonymous_user = AnonymousUser.objects.get(id=anon_user_id)
            except AnonymousUser.DoesNotExist:
                return Response({'error': 'Usuario anónimo no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        # Obtener timeline
        timeline_data = SuspiciousActivityAnalyzer.get_activity_timeline(
            ip_address=ip_address,
            user=user,
            anonymous_user=anonymous_user,
            days=days
        )

        # Obtener análisis de patrones
        pattern_analysis = SuspiciousActivityDetector.analyze_user_pattern(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            days=days
        )

        # Verificar si está bloqueado
        is_blocked = False
        block_info = None

        if ip_address:
            block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()
            if block and block.is_effective:
                is_blocked = True
                block_info = {
                    'id': block.id,
                    'reason': block.reason,
                    'blocked_by': block.blocked_by.get_full_name() if block.blocked_by else None,
                    'created_at': block.created_at,
                    'expires_at': block.expires_at,
                    'notes': block.notes
                }

        return Response({
            'query': {
                'ip_address': ip_address,
                'user_id': user_id,
                'anon_user_id': anon_user_id,
                'days': days
            },
            'is_blocked': is_blocked,
            'block_info': block_info,
            'pattern_analysis': pattern_analysis,
            'timeline': timeline_data
        })


class BlockIPView(APIView):
    """
    Endpoint para bloquear una IP.
    Solo accesible para ADMIN.

    POST /api/v1/bot/block-ip/
    Body:
    {
        "ip_address": "192.168.1.1",
        "reason": "ABUSE",
        "notes": "Usuario abusando del límite diario repetidamente",
        "expires_at": "2025-02-01T00:00:00Z"  // Opcional, null = permanente
    }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        ip_address = request.data.get('ip_address')
        reason = request.data.get('reason')
        notes = request.data.get('notes', '')
        expires_at = request.data.get('expires_at')

        # Validaciones
        if not ip_address:
            return Response(
                {'error': 'ip_address es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not reason:
            return Response(
                {'error': 'reason es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar que reason sea válido
        if reason not in [choice[0] for choice in IPBlocklist.BlockReason.choices]:
            return Response(
                {'error': f'reason inválido. Debe ser uno de: {[choice[0] for choice in IPBlocklist.BlockReason.choices]}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar si ya está bloqueada
        existing_block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()
        if existing_block and existing_block.is_effective:
            return Response(
                {'error': 'Esta IP ya está bloqueada', 'block': {
                    'id': existing_block.id,
                    'reason': existing_block.reason,
                    'created_at': existing_block.created_at
                }},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parsear expires_at si se proporcionó
        expires_at_parsed = None
        if expires_at:
            from django.utils.dateparse import parse_datetime
            expires_at_parsed = parse_datetime(expires_at)
            if not expires_at_parsed:
                return Response(
                    {'error': 'Formato de expires_at inválido. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Crear bloqueo
        block = IPBlocklist.objects.create(
            ip_address=ip_address,
            reason=reason,
            notes=notes,
            blocked_by=request.user,
            expires_at=expires_at_parsed,
            is_active=True
        )

        logger.warning(
            "IP bloqueada: %s por %s. Razón: %s",
            ip_address, request.user.get_full_name(), block.get_reason_display()
        )

        return Response({
            'success': True,
            'message': f'IP {ip_address} bloqueada exitosamente',
            'block': {
                'id': block.id,
                'ip_address': block.ip_address,
                'reason': block.reason,
                'reason_display': block.get_reason_display(),
                'notes': block.notes,
                'blocked_by': block.blocked_by.get_full_name(),
                'created_at': block.created_at,
                'expires_at': block.expires_at,
                'is_permanent': block.expires_at is None
            }
        }, status=status.HTTP_201_CREATED)


class UnblockIPView(APIView):
    """
    Endpoint para desbloquear una IP.
    Solo accesible para ADMIN.

    POST /api/v1/bot/unblock-ip/
    Body:
    {
        "ip_address": "192.168.1.1"
    }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        ip_address = request.data.get('ip_address')

        if not ip_address:
            return Response(
                {'error': 'ip_address es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Buscar bloqueo activo
        block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()

        if not block:
            return Response(
                {'error': 'No se encontró un bloqueo activo para esta IP'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Desactivar bloqueo
        block.is_active = False
        block.save()

        logger.info(
            "IP desbloqueada: %s por %s",
            ip_address, request.user.get_full_name()
        )

        return Response({
            'success': True,
            'message': f'IP {ip_address} desbloqueada exitosamente'
        })


class BotTaskStatusView(APIView):
    """
    Endpoint para verificar el estado de una tarea de procesamiento de mensaje.

    Permite al frontend hacer polling para obtener la respuesta del bot
    cuando está siendo procesada en la cola.

    GET /api/v1/bot/task-status/<task_id>/
    """
    permission_classes = [AllowAny]  # Usuarios anónimos también pueden verificar

    def get(self, request, task_id):
        """
        Verifica el estado de una tarea de Celery.

        Returns:
            - status: 'pending' | 'processing' | 'success' | 'failure'
            - reply: Respuesta del bot (solo si success)
            - meta: Metadatos de la respuesta
            - progress: Posición en cola (opcional)
        """
        from celery.result import AsyncResult

        try:
            result = AsyncResult(task_id)

            if result.ready():
                # Tarea completada
                if result.successful():
                    task_result = result.result

                    if isinstance(task_result, dict) and 'error' not in task_result:
                        return Response({
                            'status': 'success',
                            'reply': task_result.get('reply'),
                            'meta': task_result.get('meta', {})
                        })
                    else:
                        return Response({
                            'status': 'failure',
                            'error': task_result.get('error', 'Error desconocido'),
                            'details': task_result.get('details')
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    # Tarea falló
                    return Response({
                        'status': 'failure',
                        'error': 'Error procesando mensaje',
                        'details': str(result.info)
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Tarea aún procesando
                task_state = result.state

                response_data = {
                    'status': 'processing' if task_state == 'STARTED' else 'pending',
                    'message': 'Tu mensaje está siendo procesado. Por favor espera...'
                }

                # Si hay info adicional (ej: posición en cola)
                if result.info:
                    response_data['info'] = result.info

                return Response(response_data)

        except Exception as e:
            logger.exception("Error verificando estado de tarea %s: %s", task_id, e)
            return Response({
                'status': 'error',
                'error': 'No se pudo verificar el estado de la tarea'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


