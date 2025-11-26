"""
Tareas Celery para el módulo bot.

CORRECCIÓN CRÍTICA: Monitoreo de costos de tokens de Gemini.
NUEVA FUNCIONALIDAD: Cola con rate limiting para Gemini API.
"""
import logging
import time
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Count, Avg
from django.core.cache import cache
from celery import shared_task
from celery.exceptions import Retry

from .models import BotConversationLog

logger = logging.getLogger(__name__)

# Rate limit para Gemini API (plan gratuito: 15 RPM)
GEMINI_RATE_LIMIT_KEY = "gemini_api_rate_limit"
GEMINI_MAX_REQUESTS_PER_MINUTE = 15


def _check_rate_limit():
    """
    Verifica si podemos hacer una request a Gemini sin exceder el límite.
    Usa una ventana deslizante de 60 segundos.

    Returns:
        tuple: (can_proceed: bool, wait_seconds: int)
    """
    now = time.time()
    window_start = now - 60  # Ventana de 1 minuto

    # Obtener timestamps de requests recientes
    recent_requests = cache.get(GEMINI_RATE_LIMIT_KEY, [])

    # Filtrar solo los del último minuto
    recent_requests = [ts for ts in recent_requests if ts > window_start]

    if len(recent_requests) < GEMINI_MAX_REQUESTS_PER_MINUTE:
        # Hay espacio, agregar timestamp actual
        recent_requests.append(now)
        cache.set(GEMINI_RATE_LIMIT_KEY, recent_requests, 70)  # TTL 70s por seguridad
        return True, 0
    else:
        # Límite alcanzado, calcular cuánto esperar
        oldest_request = min(recent_requests)
        wait_seconds = int(oldest_request + 60 - now) + 1
        return False, wait_seconds


@shared_task(bind=True, max_retries=5, default_retry_delay=5)
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
        can_proceed, wait_seconds = _check_rate_limit()

        if not can_proceed:
            logger.warning(
                "⏳ Rate limit alcanzado (15 RPM). Reintentando en %d segundos. Task: %s",
                wait_seconds,
                self.request.id
            )
            raise self.retry(countdown=wait_seconds, exc=Retry())

        # Importaciones locales
        from .services import (
            GeminiService, 
            PromptOrchestrator, 
            ConversationMemoryService
        )
        from .notifications import HandoffNotificationService
        from .models import AnonymousUser, HumanHandoffRequest
        from .security import BotSecurityService
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


@shared_task
def report_daily_token_usage():
    """
    Reporta el uso diario de tokens y costos estimados.
    
    Esta tarea debe ejecutarse diariamente para monitorear el consumo
    de la API de Gemini y detectar patrones anómalos de uso.
    
    Los precios y umbrales de alerta se configuran desde el admin
    en el modelo BotConfiguration.
    """
    from .models import BotConfiguration
    
    # Obtener configuración actual (precios y umbrales)
    config = BotConfiguration.objects.filter(is_active=True).first()
    if not config:
        logger.error("No hay configuración activa del bot. No se puede generar reporte de costos.")
        return {'error': 'No active bot configuration'}
    
    # Precios configurables desde el admin
    input_price_per_1k = config.api_input_price_per_1k
    output_price_per_1k = config.api_output_price_per_1k
    cost_alert_threshold = config.daily_cost_alert_threshold
    tokens_alert_threshold = config.avg_tokens_alert_threshold
    
    today = timezone.now().date()
    yesterday = today - timezone.timedelta(days=1)
    
    # Estadísticas del día anterior
    logs = BotConversationLog.objects.filter(
        created_at__date=yesterday
    )
    
    # Agregaciones separadas para cálculo preciso de costos
    stats = logs.aggregate(
        total_conversations=Count('id'),
        total_tokens=Sum('tokens_used'),
        avg_tokens=Avg('tokens_used'),
        blocked_conversations=Count('id', filter=models.Q(was_blocked=True)),
    )
    
    total_tokens = stats['total_tokens'] or 0
    total_conversations = stats['total_conversations'] or 0
    avg_tokens = stats['avg_tokens'] or 0
    blocked_count = stats['blocked_conversations'] or 0
    
    # Calcular tokens de input y output por separado
    # Extraemos de response_meta los tokens específicos
    total_input_tokens = 0
    total_output_tokens = 0
    
    for log in logs:
        meta = log.response_meta or {}
        total_input_tokens += meta.get('prompt_tokens', 0)
        total_output_tokens += meta.get('completion_tokens', 0)
    
    # Si no tenemos desglose, estimamos (60% input, 40% output es típico)
    if total_input_tokens == 0 and total_output_tokens == 0 and total_tokens > 0:
        total_input_tokens = int(total_tokens * 0.6)
        total_output_tokens = int(total_tokens * 0.4)
    
    # Cálculo de costos usando precios configurables
    input_cost = Decimal(total_input_tokens) / Decimal(1000) * input_price_per_1k
    output_cost = Decimal(total_output_tokens) / Decimal(1000) * output_price_per_1k
    estimated_cost = input_cost + output_cost
    
    # Logging de estadísticas
    logger.info(
        "📊 Reporte Diario de Bot - %s\n"
        "  Conversaciones: %d\n"
        "  Tokens totales: %d (Input: %d, Output: %d)\n"
        "  Tokens promedio: %.1f\n"
        "  Bloqueadas: %d (%.1f%%)\n"
        "  Costo estimado: $%.4f USD (Input: $%.4f, Output: $%.4f)\n"
        "  Precios configurados: Input=$%.6f/1K, Output=$%.6f/1K",
        yesterday.strftime('%Y-%m-%d'),
        total_conversations,
        total_tokens,
        total_input_tokens,
        total_output_tokens,
        avg_tokens,
        blocked_count,
        (blocked_count / total_conversations * 100) if total_conversations > 0 else 0,
        estimated_cost,
        input_cost,
        output_cost,
        input_price_per_1k,
        output_price_per_1k
    )
    
    # ALERTA: Si el costo diario excede el umbral configurado
    if estimated_cost > cost_alert_threshold:
        logger.warning(
            "⚠️ ALERTA DE COSTOS: El uso de tokens del bot excedió $%.2f USD/día. "
            "Costo estimado: $%.2f USD. Revisar patrones de uso.",
            cost_alert_threshold,
            estimated_cost
        )
    
    # ALERTA: Si el promedio de tokens excede el umbral configurado
    if avg_tokens > tokens_alert_threshold:
        logger.warning(
            "⚠️ ALERTA DE EFICIENCIA: El promedio de tokens por conversación es alto (%.1f). "
            "Umbral configurado: %d. Considerar optimizar el prompt o reducir el contexto.",
            avg_tokens,
            tokens_alert_threshold
        )
    
    # ALERTA: Si más del 10% de conversaciones son bloqueadas
    if total_conversations > 0 and (blocked_count / total_conversations) > 0.1:
        logger.warning(
            "⚠️ ALERTA DE SEGURIDAD: Más del 10%% de conversaciones fueron bloqueadas (%d/%d). "
            "Revisar patrones de abuso o ajustar filtros de seguridad.",
            blocked_count,
            total_conversations
        )
    
    return {
        'date': yesterday.isoformat(),
        'total_conversations': total_conversations,
        'total_tokens': total_tokens,
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'avg_tokens': float(avg_tokens),
        'blocked_conversations': blocked_count,
        'estimated_cost_usd': float(estimated_cost),
        'input_cost_usd': float(input_cost),
        'output_cost_usd': float(output_cost),
        'input_price_per_1k': float(input_price_per_1k),
        'output_price_per_1k': float(output_price_per_1k),
    }


@shared_task
def cleanup_old_bot_logs(days_to_keep=None):
    """
    BOT-PII-PLAIN: Limpia logs antiguos del bot para mantener la base de datos optimizada
    y cumplir con políticas de retención de datos (GDPR/LGPD).
    
    Args:
        days_to_keep: Número de días de logs a mantener.
                     Si es None, usa BOT_LOG_RETENTION_DAYS de settings (default: 30)
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    from django.conf import settings
    
    # Usar configuración de settings si no se especifica
    if days_to_keep is None:
        days_to_keep = getattr(settings, 'BOT_LOG_RETENTION_DAYS', 30)
    
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
    
    # Contar logs a eliminar
    old_logs = BotConversationLog.objects.filter(created_at__lt=cutoff_date)
    count = old_logs.count()
    
    if count > 0:
        # Eliminar en lotes para evitar bloqueos largos
        deleted = old_logs.delete()
        logger.info(
            "🧹 Limpieza de logs del bot: Eliminados %d registros anteriores a %s (retención: %d días)",
            count,
            cutoff_date.strftime('%Y-%m-%d'),
            days_to_keep
        )
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }
    else:
        logger.info("🧹 Limpieza de logs del bot: No hay registros antiguos para eliminar")
        return {
            'deleted_count': 0,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }


@shared_task
def cleanup_old_handoffs(days_to_keep=None):
    """
    BOT-PII-PLAIN: Limpia solicitudes de handoff resueltas antiguas.
    
    Args:
        days_to_keep: Número de días de handoffs resueltos a mantener.
                     Si es None, usa BOT_HANDOFF_RETENTION_DAYS de settings (default: 90)
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    from django.conf import settings
    from .models import HumanHandoffRequest
    
    # Usar configuración de settings si no se especifica
    if days_to_keep is None:
        days_to_keep = getattr(settings, 'BOT_HANDOFF_RETENTION_DAYS', 90)
    
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
    
    # Solo eliminar handoffs RESUELTOS antiguos
    old_handoffs = HumanHandoffRequest.objects.filter(
        status=HumanHandoffRequest.Status.RESOLVED,
        resolved_at__lt=cutoff_date
    )
    count = old_handoffs.count()
    
    if count > 0:
        deleted = old_handoffs.delete()
        logger.info(
            "🧹 Limpieza de handoffs: Eliminados %d handoffs resueltos anteriores a %s (retención: %d días)",
            count,
            cutoff_date.strftime('%Y-%m-%d'),
            days_to_keep
        )
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }
    else:
        logger.info("🧹 Limpieza de handoffs: No hay handoffs antiguos para eliminar")
        return {
            'deleted_count': 0,
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': days_to_keep,
        }


@shared_task
def monitor_bot_health():
    """
    MEJORA #13: Monitorea salud del bot y envía alertas si hay degradación.

    Verifica:
    - Latencia promedio (alerta si > 5000ms)
    - Tasa de bloqueo (alerta si > 20%)

    Se ejecuta cada 5 minutos.
    """
    from django.db.models import Avg, Count, Q
    from django.utils import timezone
    from datetime import timedelta

    # Últimos 5 minutos
    cutoff = timezone.now() - timedelta(minutes=5)
    recent_logs = BotConversationLog.objects.filter(created_at__gte=cutoff)

    if not recent_logs.exists():
        return {'status': 'no_activity'}

    # Calcular métricas
    stats = recent_logs.aggregate(
        total=Count('id'),
        blocked=Count('id', filter=Q(was_blocked=True)),
        avg_latency=Avg('latency_ms'),
    )

    total = stats['total'] or 0
    blocked = stats['blocked'] or 0
    avg_latency = stats['avg_latency'] or 0

    # Calcular tasa de bloqueo
    block_rate = (blocked / total) * 100 if total > 0 else 0

    # Alertas
    alerts = []

    if block_rate > 20:
        logger.error(
            "⚠️ ALERTA: Tasa de bloqueo alta: %.1f%% (%d/%d) en últimos 5min",
            block_rate, blocked, total
        )
        alerts.append(f"block_rate_high_{block_rate:.1f}%")

    if avg_latency > 5000:  # 5 segundos
        logger.error(
            "⚠️ ALERTA: Latencia alta: %.0fms promedio en últimos 5min",
            avg_latency
        )
        alerts.append(f"latency_high_{avg_latency:.0f}ms")

    result = {
        'total_requests': total,
        'blocked': blocked,
        'block_rate': round(block_rate, 2),
        'avg_latency_ms': round(avg_latency, 2),
        'alerts': alerts,
    }

    if alerts:
        logger.warning("🚨 Health check completado con %d alerta(s): %s", len(alerts), result)
    else:
        logger.info("✅ Health check OK: %s", result)

    return result


@shared_task
def cleanup_expired_anonymous_users():
    """
    CORRECCIÓN SEGURIDAD: Limpia usuarios anónimos expirados para prevenir
    crecimiento excesivo de la base de datos.

    Esta tarea debe ejecutarse diariamente para eliminar sesiones expiradas
    que no fueron convertidas a usuarios registrados.

    Returns:
        dict: Estadísticas de la limpieza
    """
    from .models import AnonymousUser

    now = timezone.now()

    # Eliminar usuarios anónimos expirados y no convertidos
    expired_query = AnonymousUser.objects.filter(
        expires_at__lt=now,
        converted_to_user__isnull=True
    )

    count = expired_query.count()

    if count > 0:
        deleted_count, _ = expired_query.delete()
        logger.info(
            "🧹 Limpieza de sesiones anónimas: Eliminados %d usuarios expirados",
            deleted_count
        )
        return {
            'deleted_count': deleted_count,
            'cleanup_date': now.isoformat(),
        }
        return {
            'deleted_count': 0,
            'cleanup_date': now.isoformat(),
        }


@shared_task
def check_handoff_timeout(handoff_id):
    """
    Verifica si un handoff ha sido atendido después de 5 minutos.
    Si sigue PENDING, lo marca como EXPIRED y notifica al admin.
    """
    from .models import HumanHandoffRequest, HumanMessage
    from .notifications import HandoffNotificationService
    
    try:
        handoff = HumanHandoffRequest.objects.get(id=handoff_id)
    except HumanHandoffRequest.DoesNotExist:
        logger.error("Handoff %s no encontrado para check de timeout", handoff_id)
        return

    # Si ya no está PENDING, ignorar (ya fue atendido o cancelado)
    if handoff.status != HumanHandoffRequest.Status.PENDING:
        return

    # Marcar como EXPIRED
    handoff.status = HumanHandoffRequest.Status.EXPIRED
    handoff.save()

    # Mensaje automático de disculpa
    msg_text = (
        "Lo sentimos, en este momento el personal no se encuentra disponible. "
        "Puedes consultar de nuevo luego, dejarnos tu número para contactarte "
        "o solicitar tu cita y aclarar dudas cuando te acerques a nuestra sede."
    )
    
    HumanMessage.objects.create(
        handoff_request=handoff,
        message=msg_text,
        is_from_staff=True, # Simula ser del staff/sistema
        sender=None # Sistema
    )

    # Notificar al admin
    HandoffNotificationService.send_expired_handoff_notification(handoff)
    
    logger.warning("Handoff %s expiró sin atención. Notificaciones enviadas.", handoff_id)
