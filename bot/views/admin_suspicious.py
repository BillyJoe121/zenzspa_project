import logging

from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import SuspiciousActivity
from ..suspicious_activity_detector import SuspiciousActivityAnalyzer

logger = logging.getLogger(__name__)


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
        days = int(request.query_params.get("days", 7))
        min_severity = int(
            request.query_params.get(
                "min_severity", SuspiciousActivity.SeverityLevel.MEDIUM
            )
        )

        # Obtener resumen de usuarios sospechosos
        suspicious_users = SuspiciousActivityAnalyzer.get_suspicious_users_summary(
            days=days, min_severity=min_severity
        )

        return Response(
            {
                "period_days": days,
                "min_severity": min_severity,
                "total_suspicious_ips": len(suspicious_users),
                "suspicious_users": suspicious_users,
            }
        )
