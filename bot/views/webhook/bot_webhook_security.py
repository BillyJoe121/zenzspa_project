import hashlib
import logging
import re
import time
import uuid

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from ...models import AnonymousUser
from ...security import BotSecurityService
from ...suspicious_activity_detector import SuspiciousActivityDetector
from .utils import get_client_ip

logger = logging.getLogger(__name__)


class BotWebhookSecurityMixin:
    def _get_or_create_anonymous_user(self, request):
        """
        Obtiene o crea un usuario anónimo basado en session_id o crea uno nuevo.
        Retorna una tupla (anonymous_user, user_id_for_security)
        """
        # Intentar obtener session_id del request (header o body)
        session_id = request.data.get("session_id") or request.headers.get("X-Session-ID")

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
                                session_id,
                                anon_user.ip_address,
                                ip_address,
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
        anon_user = AnonymousUser.objects.create(ip_address=ip_address)
        logger.info("Nuevo usuario anónimo creado: %s desde IP %s", anon_user.session_id, ip_address)

        return anon_user, f"anon_{anon_user.pk}"

    def prepare_request_context(self, request):
        # CORRECCIÓN SEGURIDAD: Primero validar el mensaje antes de crear objetos en BD

        # 1. Validar tipo de dato del mensaje (Evitar AttributeError en .strip())
        raw_message = request.data.get("message")
        if raw_message is not None and not isinstance(raw_message, str):
            return Response(
                {"error": "Formato inválido. El mensaje debe ser texto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_message = (raw_message or "").strip()

        if not user_message:
            return Response(
                {"error": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST,
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
                status=status.HTTP_403_FORBIDDEN,
            )

        # 1. ¿Está el usuario castigado actualmente?
        is_blocked, reason = security.is_blocked()
        if is_blocked:
            return Response({"reply": reason, "meta": {"blocked": True}}, status=status.HTTP_403_FORBIDDEN)

        # 2. Validación de longitud (Payload size)
        valid_len, len_error = security.validate_input_length(user_message)
        if not valid_len:
            return Response({"error": len_error}, status=status.HTTP_400_BAD_REQUEST)

        # 2.5 CORRECCIÓN CRÍTICA: Validación de contenido (Jailbreak detection)
        valid_content, content_error = security.validate_input_content(user_message)
        if not valid_content:
            # Registrar intento de jailbreak
            SuspiciousActivityDetector.detect_jailbreak_attempt(user, anonymous_user, client_ip, user_message)
            return Response({"error": content_error}, status=status.HTTP_400_BAD_REQUEST)

        # 2.6 LÍMITE DIARIO: Verificar que no exceda límites (30 por usuario, 50 por IP)
        exceeded_daily, daily_error = security.check_daily_limit(ip_address=client_ip)
        if exceeded_daily:
            # Registrar abuso de límite diario
            # Extraer el conteo actual del mensaje de error si es posible
            match = re.search(r"(\d+)/(\d+)", daily_error)
            current_count = int(match.group(1)) if match else 50
            limit = int(match.group(2)) if match else 50

            SuspiciousActivityDetector.detect_daily_limit_abuse(
                user,
                anonymous_user,
                client_ip,
                current_count,
                limit,
            )
            return Response(
                {"reply": daily_error, "meta": {"blocked": True, "reason": "daily_limit"}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # ---------------------------------------------------------
        # CORRECCIÓN CRÍTICA: DEDUPLICACIÓN DE REQUESTS
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
                user_id_for_security,
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
                        user,
                        anonymous_user,
                        client_ip,
                    )
                    return Response(
                        {
                            "reply": "Estás enviando mensajes demasiado rápido. Acceso pausado por 24h.",
                            "meta": {"blocked": True},
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                # 4. CHEQUEO DE REPETICIÓN (Fuzzy Matching)
                # Si el mensaje es muy similar a los anteriores.
                if security.check_repetition(user_message):
                    # Registrar mensajes repetitivos
                    SuspiciousActivityDetector.detect_repetitive_messages(
                        user,
                        anonymous_user,
                        client_ip,
                        user_message,
                    )
                    return Response(
                        {
                            "reply": "Hemos detectado mensajes repetitivos. Acceso pausado por 24h.",
                            "meta": {"blocked": True},
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                # Éxito, salir del loop
                break

            except BlockingIOError:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Lock contention para usuario %s, reintentando (%d/%d)",
                        user_id_for_security,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(0.1 * (attempt + 1))  # Backoff exponencial: 0.1s, 0.2s
                    continue
                else:
                    # Último intento falló
                    logger.error(
                        "Lock contention persistente para usuario %s después de %d intentos",
                        user_id_for_security,
                        MAX_RETRIES,
                    )
                    return Response(
                        {"error": "El sistema está experimentando alta carga. Intenta en unos segundos."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )

        timings["security_checks"] = time.time() - security_start

        return {
            "user": user,
            "anonymous_user": anonymous_user,
            "user_id_for_security": user_id_for_security,
            "security": security,
            "client_ip": client_ip,
            "user_message": user_message,
            "dedup_id": dedup_id,
            "dedup_key": dedup_key,
            "dedup_window": dedup_window,
            "timings": timings,
            "start_time": start_time,
        }
