import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import BotConversationLog

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
        from django.db.models import Avg, Count, Q, Sum

        # Parámetros
        days = int(request.query_params.get("days", 7))
        since = timezone.now() - timedelta(days=days)

        # Estadísticas por IP
        ip_stats = (
            BotConversationLog.objects.filter(
                created_at__gte=since,
                ip_address__isnull=False,
            )
            .values("ip_address")
            .annotate(
                total_messages=Count("id"),
                total_tokens=Sum("tokens_used"),
                blocked_count=Count("id", filter=Q(was_blocked=True)),
                avg_tokens_per_msg=Avg("tokens_used"),
                avg_latency_ms=Avg("latency_ms"),
            )
            .order_by("-total_messages")
        )

        # IPs sospechosas (>40 mensajes/día en promedio)
        suspicious_threshold = 40 * days
        suspicious_ips = []

        for ip in ip_stats:
            avg_per_day = ip["total_messages"] / days
            ip["avg_messages_per_day"] = round(avg_per_day, 1)

            if ip["total_messages"] > suspicious_threshold:
                suspicious_ips.append(
                    {
                        "ip_address": ip["ip_address"],
                        "total_messages": ip["total_messages"],
                        "avg_per_day": round(avg_per_day, 1),
                        "total_tokens": ip["total_tokens"],
                        "blocked_count": ip["blocked_count"],
                    }
                )

        # Estadísticas generales
        total_stats = BotConversationLog.objects.filter(created_at__gte=since).aggregate(
            total_conversations=Count("id"),
            total_tokens=Sum("tokens_used"),
            total_blocked=Count("id", filter=Q(was_blocked=True)),
            avg_latency=Avg("latency_ms"),
        )

        # Conteo de IPs únicas
        unique_ips = (
            BotConversationLog.objects.filter(
                created_at__gte=since,
                ip_address__isnull=False,
            )
            .values("ip_address")
            .distinct()
            .count()
        )

        return Response(
            {
                "period_days": days,
                "since": since.isoformat(),
                "summary": {
                    "total_conversations": total_stats["total_conversations"] or 0,
                    "total_tokens_consumed": total_stats["total_tokens"] or 0,
                    "total_blocked": total_stats["total_blocked"] or 0,
                    "avg_latency_ms": round(total_stats["avg_latency"] or 0, 2),
                    "unique_ips": unique_ips,
                },
                "top_ips": list(ip_stats[:20]),
                "suspicious_ips": suspicious_ips,
                "suspicious_count": len(suspicious_ips),
            }
        )
