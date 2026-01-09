"""
Vistas administrativas relacionadas con seguridad (bloqueo de IPs).
"""
from django.core.cache import cache
from rest_framework import status, views
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response


class BlockIPView(views.APIView):
    """Bloquea una IP temporalmente."""

    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        ip = request.data.get("ip")
        ttl = int(request.data.get("ttl", 3600))

        if not ip:
            return Response({"detail": "IP requerida."}, status=status.HTTP_400_BAD_REQUEST)

        cache.set(f"blocked_ip:{ip}", True, timeout=ttl)
        return Response({"detail": f"IP {ip} bloqueada por {ttl} segundos."}, status=status.HTTP_200_OK)
