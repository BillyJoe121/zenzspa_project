"""
Middleware de seguridad para el módulo users.

Implementa verificación de dispositivos bloqueados y otras funcionalidades
de seguridad a nivel de petición HTTP.
"""
import hashlib
import logging

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .models import BlockedDevice

logger = logging.getLogger(__name__)


class BlockedDeviceMiddleware(MiddlewareMixin):
    """
    Middleware que bloquea peticiones de dispositivos marcados como bloqueados.

    Genera un fingerprint del dispositivo basado en User-Agent y lo compara
    con la lista de dispositivos bloqueados. Si el dispositivo está bloqueado,
    retorna HTTP 403 Forbidden.

    El fingerprint se genera como hash SHA256 del User-Agent para permitir
    búsquedas rápidas en base de datos.
    """

    def process_request(self, request):
        """
        Verifica si el dispositivo está bloqueado antes de procesar la petición.

        Args:
            request: HttpRequest object

        Returns:
            JsonResponse con HTTP 403 si el dispositivo está bloqueado,
            None para permitir que la petición continúe normalmente.
        """
        # Generar fingerprint del dispositivo
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if not user_agent:
            # Si no hay user agent, permitir la petición
            return None

        # Crear hash del user agent como fingerprint
        device_fingerprint = hashlib.sha256(user_agent.encode()).hexdigest()

        # Verificar si el dispositivo está bloqueado
        try:
            blocked_device = BlockedDevice.objects.filter(
                device_fingerprint=device_fingerprint,
                is_blocked=True
            ).first()

            if blocked_device:
                logger.warning(
                    f"Petición bloqueada de dispositivo: {device_fingerprint[:16]}... "
                    f"Razón: {blocked_device.reason}"
                )
                return JsonResponse(
                    {
                        'detail': 'Tu dispositivo ha sido bloqueado. Contacta al administrador.',
                        'code': 'DEVICE_BLOCKED'
                    },
                    status=403
                )
        except Exception as e:
            # En caso de error, permitir la petición (fail open)
            logger.error(f"Error verificando dispositivo bloqueado: {e}")
            return None

        return None


def block_device_by_user_agent(user_agent: str, reason: str = "", ip_address: str = None, user=None):
    """
    Bloquea un dispositivo basado en su User-Agent.

    Función helper para bloquear dispositivos desde cualquier parte del código.

    Args:
        user_agent: String del User-Agent del dispositivo
        reason: Razón del bloqueo (opcional)
        ip_address: IP del dispositivo (opcional)
        user: Usuario asociado al bloqueo (opcional)

    Returns:
        BlockedDevice: Objeto creado o existente

    Ejemplo:
        from users.middleware import block_device_by_user_agent

        # Bloquear dispositivo sospechoso
        block_device_by_user_agent(
            user_agent=request.META['HTTP_USER_AGENT'],
            reason="Actividad sospechosa detectada",
            ip_address=request.META['REMOTE_ADDR'],
            user=request.user
        )
    """
    device_fingerprint = hashlib.sha256(user_agent.encode()).hexdigest()

    blocked_device, created = BlockedDevice.objects.get_or_create(
        device_fingerprint=device_fingerprint,
        defaults={
            'user_agent': user_agent,
            'ip_address': ip_address,
            'reason': reason,
            'is_blocked': True,
            'user': user if user and user.is_authenticated else None,
        }
    )

    if not created and not blocked_device.is_blocked:
        # Si existía pero estaba desbloqueado, volver a bloquear
        blocked_device.is_blocked = True
        blocked_device.reason = reason
        blocked_device.save(update_fields=['is_blocked', 'reason', 'updated_at'])

    logger.info(
        f"Dispositivo bloqueado: {device_fingerprint[:16]}... Razón: {reason}"
    )

    return blocked_device
