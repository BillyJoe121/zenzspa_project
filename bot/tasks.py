"""
Tareas Celery para el módulo bot.

CORRECCIÓN CRÍTICA: Monitoreo de costos de tokens de Gemini.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Count, Avg
from celery import shared_task

from .models import BotConversationLog

logger = logging.getLogger(__name__)


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
def cleanup_old_bot_logs(days_to_keep=90):
    """
    Limpia logs antiguos del bot para mantener la base de datos optimizada.
    
    Args:
        days_to_keep: Número de días de logs a mantener (default: 90)
    
    Returns:
        dict: Estadísticas de la limpieza
    """
    cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
    
    # Contar logs a eliminar
    old_logs = BotConversationLog.objects.filter(created_at__lt=cutoff_date)
    count = old_logs.count()
    
    if count > 0:
        # Eliminar en lotes para evitar bloqueos largos
        deleted = old_logs.delete()
        logger.info(
            "🧹 Limpieza de logs del bot: Eliminados %d registros anteriores a %s",
            count,
            cutoff_date.strftime('%Y-%m-%d')
        )
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date.isoformat(),
        }
    else:
        logger.info("🧹 Limpieza de logs del bot: No hay registros antiguos para eliminar")
        return {
            'deleted_count': 0,
            'cutoff_date': cutoff_date.isoformat(),
        }
