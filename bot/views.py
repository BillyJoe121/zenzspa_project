import hashlib
import logging
import time

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import PromptOrchestrator, GeminiService
from .security import BotSecurityService
from .throttling import BotRateThrottle, BotDailyThrottle
from .models import BotConversationLog, BotConfiguration

logger = logging.getLogger(__name__)


class BotWebhookView(APIView):
    permission_classes = [IsAuthenticated]
    # CORRECCIÓN CRÍTICA: Aplicar throttle por minuto Y diario
    throttle_classes = [BotRateThrottle, BotDailyThrottle]

    def post(self, request):
        user = request.user
        security = BotSecurityService(user)
        
        # CORRECCIÓN CRÍTICA: Tracking de latencia para auditoría
        start_time = time.time()

        # ---------------------------------------------------------
        # NIVEL 1: BLOQUEOS PREVIOS (Costo computacional: Muy bajo)
        # ---------------------------------------------------------

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
            f"{user.id}:{user_message}:{int(time.time() / dedup_window)}".encode()
        ).hexdigest()[:16]
        dedup_key = f"bot:dedup:{dedup_id}"
        
        # Verificar si ya procesamos este mensaje recientemente
        cached_response = cache.get(dedup_key)
        if cached_response:
            logger.info(
                "Request duplicado detectado para user %s. Devolviendo respuesta cacheada.",
                user.id
            )
            return Response(cached_response)

        # 3. CHEQUEO DE VELOCIDAD (Protección de Billetera)
        # Si envía muchos mensajes en < 60s, se bloquea por script/bot malicioso.
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
        except BlockingIOError:
            # Alta concurrencia: no pudimos adquirir el lock
            logger.error("Lock contention para usuario %s en security checks", user.id)
            return Response(
                {"error": "El sistema está experimentando alta carga. Intenta en unos segundos."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # ---------------------------------------------------------
        # NIVEL 2: INTELIGENCIA ARTIFICIAL (Costo: Tokens / Latencia)
        # ---------------------------------------------------------

        orchestrator = PromptOrchestrator()
        full_prompt = orchestrator.build_full_prompt(user, user_message)

        gemini = GeminiService()

        # CORRECCIÓN: Desempaquetamos la tupla (texto, meta) correctamente
        reply_text, reply_meta = gemini.generate_response(full_prompt)

        # 5. CHEQUEO DE CONTENIDO (Safety Guardrail)
        # Verificamos si Gemini activó el bloqueo de seguridad (via metadata o keyword)
        # Esto cubre casos donde la IA devuelve "noRelated" o un error de seguridad
        if reply_meta.get("source") == "security_guardrail" or reply_text == "noRelated":
            warning_msg = security.handle_off_topic()

            # CORRECCIÓN CRÍTICA: Registrar bloqueo en auditoría
            latency_ms = int((time.time() - start_time) * 1000)
            BotConversationLog.objects.create(
                user=user,
                message=user_message,
                response=warning_msg,
                response_meta={"source": "security_guardrail", "blocked": True},
                was_blocked=True,
                block_reason="security_guardrail",
                latency_ms=latency_ms,
                tokens_used=reply_meta.get("tokens", 0),  # CORRECCIÓN: Tracking de tokens
            )

            # Devolvemos la advertencia pre-grabada
            return Response({
                "reply": warning_msg,
                "meta": {"source": "security_guardrail", "blocked": True}
            })

        # ÉXITO: Mensaje válido y procesado.
        response_data = {
            "reply": reply_text,
            "meta": reply_meta
        }
        
        # CORRECCIÓN CRÍTICA: Registrar conversación exitosa en auditoría
        latency_ms = int((time.time() - start_time) * 1000)
        BotConversationLog.objects.create(
            user=user,
            message=user_message,
            response=reply_text,
            response_meta=reply_meta,
            was_blocked=False,
            block_reason="",
            latency_ms=latency_ms,
            tokens_used=reply_meta.get("tokens", 0),  # CORRECCIÓN: Tracking de tokens
        )
        
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
