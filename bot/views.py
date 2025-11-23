import hashlib
import logging
import time
import uuid

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import PromptOrchestrator, GeminiService
from .security import BotSecurityService
from .throttling import BotRateThrottle, BotDailyThrottle, BotIPThrottle
from .models import BotConversationLog, BotConfiguration, AnonymousUser

logger = logging.getLogger(__name__)


class BotWebhookView(APIView):
    permission_classes = [AllowAny]  # Soporte para usuarios anónimos y registrados
    # CORRECCIÓN CRÍTICA: Aplicar throttle por minuto Y diario
    # MEJORA #4: Agregar throttle por IP para prevenir abuso con múltiples cuentas
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def _get_client_ip(self, request):
        """Obtiene la IP real del cliente, considerando proxies"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

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
                        # Actualizar last_activity (se hace automáticamente con auto_now)
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
        # Determinar si es usuario autenticado o anónimo
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

        # 1. ¿Está el usuario castigado actualmente?
        is_blocked, reason = security.is_blocked()
        if is_blocked:
            return Response(
                {"reply": reason, "meta": {"blocked": True}},
                status=status.HTTP_403_FORBIDDEN
            )

        user_message = (request.data.get("message") or "").strip()

        # 2. Validación de longitud (Payload size)
        valid_len, len_error = security.validate_input_length(user_message)
        if not valid_len:
            return Response(
                {"error": len_error},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_message:
            return Response(
                {"error": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2.5 CORRECCIÓN CRÍTICA: Validación de contenido (Jailbreak detection)
        valid_content, content_error = security.validate_input_content(user_message)
        if not valid_content:
            return Response(
                {"error": content_error},
                status=status.HTTP_400_BAD_REQUEST
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
                    return Response(
                        {"reply": "Estás enviando mensajes demasiado rápido. Acceso pausado por 24h.", "meta": {
                            "blocked": True}},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )

                # 4. CHEQUEO DE REPETICIÓN (Fuzzy Matching)
                # Si el mensaje es muy similar a los anteriores.
                if security.check_repetition(user_message):
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

        # Gemini API call
        gemini_start = time.time()
        gemini = GeminiService()
        reply_text, reply_meta = gemini.generate_response(full_prompt)
        timings['gemini_api'] = time.time() - gemini_start

        # 5. CHEQUEO DE CONTENIDO (Safety Guardrail)
        # Verificamos si Gemini activó el bloqueo de seguridad (via metadata o keyword)
        # Esto cubre casos donde la IA devuelve "noRelated" o un error de seguridad
        if reply_meta.get("source") == "security_guardrail" or reply_text == "noRelated":
            warning_msg = security.handle_off_topic()

            # CORRECCIÓN CRÍTICA: Registrar bloqueo en auditoría
            latency_ms = int((time.time() - start_time) * 1000)
            log_data = {
                "message": user_message,
                "response": warning_msg,
                "response_meta": {"source": "security_guardrail", "blocked": True},
                "was_blocked": True,
                "block_reason": "security_guardrail",
                "latency_ms": latency_ms,
                "tokens_used": reply_meta.get("tokens", 0),
            }
            if user:
                log_data["user"] = user
            else:
                log_data["anonymous_user"] = anonymous_user

            BotConversationLog.objects.create(**log_data)

            # Devolvemos la advertencia pre-grabada
            return Response({
                "reply": warning_msg,
                "meta": {"source": "security_guardrail", "blocked": True}
            })

        # ÉXITO: Mensaje válido y procesado.
        # MEJORA #12: Agregar timings detallados a metadata
        timings_ms = {k: round(v * 1000, 2) for k, v in timings.items()}
        reply_meta['timings'] = timings_ms

        response_data = {
            "reply": reply_text,
            "meta": reply_meta
        }

        # Para usuarios anónimos, incluir session_id en la respuesta
        if anonymous_user:
            response_data['session_id'] = str(anonymous_user.session_id)

        # CORRECCIÓN CRÍTICA: Registrar conversación exitosa en auditoría
        latency_ms = int((time.time() - start_time) * 1000)

        # MEJORA #12: Log de tiempos por componente
        logger.info(
            "Bot request timings for user %s: security=%.2fms, prompt=%.2fms, gemini=%.2fms, total=%.2fms",
            user_id_for_security,
            timings_ms.get('security_checks', 0),
            timings_ms.get('prompt_building', 0),
            timings_ms.get('gemini_api', 0),
            latency_ms
        )

        # CORRECCIÓN CRÍTICA: Registrar conversación exitosa
        log_data = {
            "message": user_message,
            "response": reply_text,
            "response_meta": reply_meta,
            "was_blocked": False,
            "block_reason": "",
            "latency_ms": latency_ms,
            "tokens_used": reply_meta.get("tokens", 0),
        }
        if user:
            log_data["user"] = user
        else:
            log_data["anonymous_user"] = anonymous_user

        BotConversationLog.objects.create(**log_data)

        # MEJORA #10: Guardar en historial de conversación
        from bot.services import ConversationMemoryService
        ConversationMemoryService.add_to_history(user_id_for_security, user_message, reply_text)

        # Cachear respuesta para deduplicación
        cache.set(dedup_key, response_data, timeout=dedup_window * 2)

        return Response(response_data)


class BotHealthCheckView(APIView):
    """
    CORRECCIÓN MODERADA: Endpoint de health check para monitoreo.
    Verifica que todos los componentes críticos del bot estén funcionando.
    """
    permission_classes = []  # Público para load balancers
    
    def get(self, request):
        checks = {
            'cache': self._check_cache(),
            'gemini_api': self._check_gemini(),
            'configuration': self._check_config(),
        }
        
        all_healthy = all(checks.values())
        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return Response({
            'status': 'healthy' if all_healthy else 'unhealthy',
            'checks': checks,
            'timestamp': time.time(),
        }, status=status_code)
    
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
    
    def _check_gemini(self) -> bool:
        """Verifica que la API key de Gemini esté configurada"""
        try:
            gemini = GeminiService()
            # Solo verificamos que la key existe, no hacemos request real
            return bool(gemini.api_key)
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
