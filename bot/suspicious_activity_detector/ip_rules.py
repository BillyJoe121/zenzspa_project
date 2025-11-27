"""
Reglas y análisis basados en IP/usuario.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Count, Sum
from django.utils import timezone

from ..models import BotConversationLog, IPBlocklist, SuspiciousActivity

logger = logging.getLogger(__name__)


def get_threshold(setting_name, default_value):
    """Obtiene umbral configurable desde settings con fallback por defecto."""
    return getattr(settings, setting_name, default_value)


def check_ip_blocked(ip_address: str) -> tuple[bool, str]:
    """
    Verifica si una IP está bloqueada.

    Returns:
        tuple[bool, str]: (is_blocked, reason)
    """
    block = IPBlocklist.objects.filter(
        ip_address=ip_address,
        is_active=True
    ).first()

    if block and block.is_effective:
        return True, (
            f"Tu IP ha sido bloqueada por: {block.get_reason_display()}. "
            f"Contacta al administrador si crees que esto es un error."
        )

    return False, ""


def analyze_user_pattern(user=None, anonymous_user=None, ip_address=None, days=7):
    """
    Analiza patrones de comportamiento de un usuario/IP para detectar anomalías.

    Returns:
        dict: Diccionario con estadísticas y flags de sospecha
    """
    since = timezone.now() - timedelta(days=days)

    # Umbrales configurables en settings
    avg_per_day_threshold = get_threshold('BOT_SUSPICIOUS_AVG_MSGS_PER_DAY', 40)
    block_rate_threshold = get_threshold('BOT_SUSPICIOUS_BLOCK_RATE_THRESHOLD', 30)
    activity_count_threshold = get_threshold('BOT_SUSPICIOUS_ACTIVITY_COUNT_THRESHOLD', 5)

    # Construir filtro base
    filter_kwargs = {'created_at__gte': since}
    if user:
        filter_kwargs['user'] = user
    elif anonymous_user:
        filter_kwargs['anonymous_user'] = anonymous_user

    # Si tenemos IP, agregar filtro por IP también
    if ip_address:
        filter_kwargs['ip_address'] = ip_address

    # Estadísticas de conversaciones
    conversations = BotConversationLog.objects.filter(**filter_kwargs)

    stats = conversations.aggregate(
        total_messages=Count('id'),
        total_blocked=Count('id', filter=models.Q(was_blocked=True)),
        total_tokens=Sum('tokens_used') or 0
    )

    # Calcular métricas
    avg_messages_per_day = stats['total_messages'] / days if days > 0 else 0
    block_rate = (stats['total_blocked'] / stats['total_messages'] * 100) if stats['total_messages'] > 0 else 0

    # Contar actividades sospechosas registradas
    suspicious_filter = filter_kwargs.copy()
    suspicious_activities = SuspiciousActivity.objects.filter(**suspicious_filter)

    suspicious_count = suspicious_activities.count()
    critical_count = suspicious_activities.filter(
        severity=SuspiciousActivity.SeverityLevel.CRITICAL
    ).count()

    # Determinar flags de sospecha
    is_suspicious = False
    suspicion_reasons = []

    if avg_messages_per_day > avg_per_day_threshold:
        is_suspicious = True
        suspicion_reasons.append(
            f"Promedio de {avg_messages_per_day:.1f} mensajes/día (límite: {avg_per_day_threshold})"
        )

    if block_rate > block_rate_threshold:
        is_suspicious = True
        suspicion_reasons.append(
            f"Tasa de bloqueo del {block_rate:.1f}% (límite: {block_rate_threshold}%)"
        )

    if suspicious_count > activity_count_threshold:
        is_suspicious = True
        suspicion_reasons.append(
            f"{suspicious_count} actividades sospechosas registradas"
        )

    if critical_count > 0:
        is_suspicious = True
        suspicion_reasons.append(f"{critical_count} actividades críticas registradas")

    return {
        'period_days': days,
        'total_messages': stats['total_messages'],
        'total_blocked': stats['total_blocked'],
        'total_tokens': stats['total_tokens'],
        'avg_messages_per_day': round(avg_messages_per_day, 1),
        'block_rate': round(block_rate, 1),
        'suspicious_activities': suspicious_count,
        'critical_activities': critical_count,
        'is_suspicious': is_suspicious,
        'suspicion_reasons': suspicion_reasons,
    }

