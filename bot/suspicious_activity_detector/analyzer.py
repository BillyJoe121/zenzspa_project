"""
Analizador para generar reportes y estadísticas de actividades sospechosas.
"""
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from ..models import BotConversationLog, IPBlocklist, SuspiciousActivity
from .ip_rules import analyze_user_pattern


class SuspiciousActivityAnalyzer:
    """Helper para dashboards y reportes de actividad sospechosa."""

    @staticmethod
    def get_suspicious_users_summary(days=7, min_severity=SuspiciousActivity.SeverityLevel.MEDIUM):
        """
        Obtiene un resumen de usuarios con actividad sospechosa reciente.

        Args:
            days: Número de días a analizar
            min_severity: Severidad mínima para considerar

        Returns:
            list: Lista de diccionarios con información de usuarios sospechosos
        """
        since = timezone.now() - timedelta(days=days)

        # Agrupar por usuario/IP
        activities = SuspiciousActivity.objects.filter(
            created_at__gte=since,
            severity__gte=min_severity
        ).select_related('user', 'anonymous_user')

        # Agrupar por IP
        ip_groups = activities.values('ip_address').annotate(
            total_activities=Count('id'),
            critical_count=Count('id', filter=Q(severity=SuspiciousActivity.SeverityLevel.CRITICAL)),
            high_count=Count('id', filter=Q(severity=SuspiciousActivity.SeverityLevel.HIGH)),
            last_activity=Max('created_at'),
            unreviewed_count=Count('id', filter=Q(reviewed=False))
        ).order_by('-critical_count', '-high_count', '-total_activities')

        results = []
        for ip_data in ip_groups:
            ip_address = ip_data['ip_address']

            # Obtener usuarios asociados a esta IP
            ip_activities = activities.filter(ip_address=ip_address)

            # Usuarios registrados
            users = ip_activities.filter(user__isnull=False).values_list('user_id', flat=True).distinct()
            # Usuarios anónimos
            anon_users = ip_activities.filter(anonymous_user__isnull=False).values_list('anonymous_user_id', flat=True).distinct()

            # Verificar si IP está bloqueada
            is_blocked = IPBlocklist.objects.filter(
                ip_address=ip_address,
                is_active=True
            ).exists()

            # Obtener actividades más recientes
            recent_activities = ip_activities.order_by('-created_at')[:5]

            # Analizar patrón
            pattern = analyze_user_pattern(
                ip_address=ip_address,
                days=days
            )

            results.append({
                'ip_address': ip_address,
                'is_blocked': is_blocked,
                'total_activities': ip_data['total_activities'],
                'critical_count': ip_data['critical_count'],
                'high_count': ip_data['high_count'],
                'unreviewed_count': ip_data['unreviewed_count'],
                'last_activity': ip_data['last_activity'],
                'registered_users_count': len(users),
                'anonymous_users_count': len(anon_users),
                'pattern_analysis': pattern,
                'recent_activities': [
                    {
                        'id': act.id,
                        'type': act.activity_type,
                        'severity': act.severity,
                        'description': act.description,
                        'created_at': act.created_at,
                        'participant': act.participant_identifier
                    }
                    for act in recent_activities
                ]
            })

        return results

    @staticmethod
    def get_activity_timeline(ip_address=None, user=None, anonymous_user=None, days=30):
        """
        Obtiene la línea de tiempo de actividades de un usuario/IP.

        Returns:
            dict: Timeline con conversaciones y actividades sospechosas
        """
        since = timezone.now() - timedelta(days=days)

        # Filtros
        conv_filter = {'created_at__gte': since}
        susp_filter = {'created_at__gte': since}

        if ip_address:
            conv_filter['ip_address'] = ip_address
            susp_filter['ip_address'] = ip_address
        if user:
            conv_filter['user'] = user
            susp_filter['user'] = user
        if anonymous_user:
            conv_filter['anonymous_user'] = anonymous_user
            susp_filter['anonymous_user'] = anonymous_user

        # Obtener conversaciones
        conversations = BotConversationLog.objects.filter(**conv_filter).order_by('created_at')

        # Obtener actividades sospechosas
        suspicious = SuspiciousActivity.objects.filter(**susp_filter).order_by('created_at')

        # Combinar en timeline
        timeline = []

        for conv in conversations:
            timeline.append({
                'type': 'conversation',
                'timestamp': conv.created_at,
                'message': conv.message[:100],
                'response': conv.response[:100],
                'was_blocked': conv.was_blocked,
                'block_reason': conv.block_reason,
                'tokens_used': conv.tokens_used,
                'id': conv.id
            })

        for susp in suspicious:
            timeline.append({
                'type': 'suspicious_activity',
                'timestamp': susp.created_at,
                'activity_type': susp.activity_type,
                'severity': susp.severity,
                'description': susp.description,
                'reviewed': susp.reviewed,
                'id': susp.id
            })

        # Ordenar por timestamp
        timeline.sort(key=lambda x: x['timestamp'])

        return {
            'period_days': days,
            'total_events': len(timeline),
            'conversations_count': conversations.count(),
            'suspicious_activities_count': suspicious.count(),
            'timeline': timeline
        }

