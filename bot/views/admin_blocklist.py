import logging

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import IPBlocklist

logger = logging.getLogger(__name__)


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
        ip_address = request.data.get("ip_address")
        reason = request.data.get("reason")
        notes = request.data.get("notes", "")
        expires_at = request.data.get("expires_at")

        # Validaciones
        if not ip_address:
            return Response({"error": "ip_address es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        if not reason:
            return Response({"error": "reason es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        # Validar que reason sea válido
        if reason not in [choice[0] for choice in IPBlocklist.BlockReason.choices]:
            return Response(
                {"error": f"reason inválido. Debe ser uno de: {[choice[0] for choice in IPBlocklist.BlockReason.choices]}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar si ya está bloqueada
        existing_block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()
        if existing_block and existing_block.is_effective:
            return Response(
                {
                    "error": "Esta IP ya está bloqueada",
                    "block": {
                        "id": existing_block.id,
                        "reason": existing_block.reason,
                        "created_at": existing_block.created_at,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parsear expires_at si se proporcionó
        expires_at_parsed = None
        if expires_at:
            from django.utils.dateparse import parse_datetime

            expires_at_parsed = parse_datetime(expires_at)
            if not expires_at_parsed:
                return Response(
                    {"error": "Formato de expires_at inválido. Use ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Crear bloqueo
        block = IPBlocklist.objects.create(
            ip_address=ip_address,
            reason=reason,
            notes=notes,
            blocked_by=request.user,
            expires_at=expires_at_parsed,
            is_active=True,
        )

        logger.warning(
            "IP bloqueada: %s por %s. Razón: %s",
            ip_address,
            request.user.get_full_name(),
            block.get_reason_display(),
        )

        return Response(
            {
                "success": True,
                "message": f"IP {ip_address} bloqueada exitosamente",
                "block": {
                    "id": block.id,
                    "ip_address": block.ip_address,
                    "reason": block.reason,
                    "reason_display": block.get_reason_display(),
                    "notes": block.notes,
                    "blocked_by": block.blocked_by.get_full_name(),
                    "created_at": block.created_at,
                    "expires_at": block.expires_at,
                    "is_permanent": block.expires_at is None,
                },
            },
            status=status.HTTP_201_CREATED,
        )


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
        ip_address = request.data.get("ip_address")

        if not ip_address:
            return Response({"error": "ip_address es requerido"}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar bloqueo activo
        block = IPBlocklist.objects.filter(ip_address=ip_address, is_active=True).first()

        if not block:
            return Response(
                {"error": "No se encontró un bloqueo activo para esta IP"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Desactivar bloqueo
        block.is_active = False
        block.save()

        logger.info("IP desbloqueada: %s por %s", ip_address, request.user.get_full_name())

        return Response({"success": True, "message": f"IP {ip_address} desbloqueada exitosamente"})
