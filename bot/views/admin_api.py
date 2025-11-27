import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AnonymousUser, BotConversationLog, IPBlocklist, SuspiciousActivity
from ..suspicious_activity_detector import SuspiciousActivityAnalyzer, SuspiciousActivityDetector

logger = logging.getLogger(__name__)


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

