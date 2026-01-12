import logging

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AnonymousUser, IPBlocklist
from ..suspicious_activity_detector import SuspiciousActivityAnalyzer, SuspiciousActivityDetector

logger = logging.getLogger(__name__)


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
        ip_address = request.query_params.get("ip")
        user_id = request.query_params.get("user_id")
        anon_user_id = request.query_params.get("anon_user_id")
        days = int(request.query_params.get("days", 30))

        # Validar que al menos uno esté presente
        if not any([ip_address, user_id, anon_user_id]):
            return Response(
                {"error": "Debe proporcionar al menos uno: ip, user_id, o anon_user_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Obtener objetos si es necesario
        from users.models import CustomUser

        user = None
        anonymous_user = None

        if user_id:
            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if anon_user_id:
            try:
                anonymous_user = AnonymousUser.objects.get(id=anon_user_id)
            except AnonymousUser.DoesNotExist:
                return Response({"error": "Usuario anónimo no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        # Obtener timeline
        timeline_data = SuspiciousActivityAnalyzer.get_activity_timeline(
            ip_address=ip_address,
            user=user,
            anonymous_user=anonymous_user,
            days=days,
        )

        # Obtener análisis de patrones
        pattern_analysis = SuspiciousActivityDetector.analyze_user_pattern(
            user=user,
            anonymous_user=anonymous_user,
            ip_address=ip_address,
            days=days,
        )

        # Verificar si está bloqueado
        is_blocked = False
        block_info = None

        if ip_address:
            block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()
            if block and block.is_effective:
                is_blocked = True
                block_info = {
                    "id": block.id,
                    "reason": block.reason,
                    "blocked_by": block.blocked_by.get_full_name() if block.blocked_by else None,
                    "created_at": block.created_at,
                    "expires_at": block.expires_at,
                    "notes": block.notes,
                }

        return Response(
            {
                "query": {
                    "ip_address": ip_address,
                    "user_id": user_id,
                    "anon_user_id": anon_user_id,
                    "days": days,
                },
                "is_blocked": is_blocked,
                "block_info": block_info,
                "pattern_analysis": pattern_analysis,
                "timeline": timeline_data,
            }
        )
