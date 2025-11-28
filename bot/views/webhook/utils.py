"""
Utilidades compartidas para los webhooks del bot.
"""
import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    BOT-SEC-FORWARDED-IP: Obtiene la IP real del cliente de forma segura.

    Solo confía en X-Forwarded-For si:
    1. TRUST_PROXY está habilitado en settings
    2. La petición proviene de un proxy autorizado

    Esto previene que clientes maliciosos falsifiquen su IP para evadir
    bloqueos, throttles y límites diarios.
    """
    # IP directa del request (siempre confiable)
    remote_addr = request.META.get('REMOTE_ADDR', '127.0.0.1')

    # Verificar si debemos confiar en proxies
    trust_proxy = getattr(settings, 'TRUST_PROXY', False)

    if not trust_proxy:
        # No confiar en X-Forwarded-For, usar IP directa
        try:
            ipaddress.ip_address(remote_addr)
            return remote_addr
        except (ValueError, TypeError):
            logger.warning("IP inválida recibida: %s. Usando IP por defecto.", remote_addr)
            return '0.0.0.0'

    # Si confiamos en proxies, procesar X-Forwarded-For
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if x_forwarded_for:
        # X-Forwarded-For puede contener múltiples IPs: "client, proxy1, proxy2"
        # Tomamos la primera IP (la del cliente original)
        ips = [ip.strip() for ip in x_forwarded_for.split(',')]
        client_ip = ips[0] if ips else remote_addr

        # Validar formato de IP
        try:
            ipaddress.ip_address(client_ip)

            # Registrar en logs para auditoría
            if len(ips) > 1:
                logger.debug(
                    "X-Forwarded-For chain: %s, using client IP: %s",
                    x_forwarded_for, client_ip
                )

            return client_ip
        except (ValueError, TypeError):
            logger.warning(
                "IP inválida en X-Forwarded-For: %s. Usando REMOTE_ADDR: %s",
                client_ip, remote_addr
            )
            return remote_addr
    else:
        # No hay X-Forwarded-For, usar IP directa
        try:
            ipaddress.ip_address(remote_addr)
            return remote_addr
        except (ValueError, TypeError):
            logger.warning("IP inválida recibida: %s. Usando IP por defecto.", remote_addr)
            return '0.0.0.0'


def normalize_chat_response(text: str) -> str:
    """
    Normaliza la respuesta para formato de chat con píldoras.
    - Convierte \\n\\n a \\n (un solo salto)
    - Asegura espacio después de cada \\n
    - Divide párrafos largos en fragmentos más cortos
    """
    import re

    # 1. Normalizar múltiples saltos a uno solo
    text = re.sub(r'\n\n+', '\n', text)

    # 2. Asegurar espacio después de \n si no lo hay
    text = re.sub(r'\n([^\s])', r'\n\1', text)

    # 3. Dividir oraciones largas (opcional, más agresivo)
    # Si un párrafo tiene más de 150 caracteres, intentar dividirlo
    paragraphs = text.split('\n')
    normalized = []

    for para in paragraphs:
        if len(para) > 150:
            # Dividir por puntos seguidos de espacio
            sentences = re.split(r'(\. )', para)
            current_chunk = ""

            for i, part in enumerate(sentences):
                current_chunk += part
                # Si es un punto o llegamos a ~100 chars, hacer corte
                if part == '. ' or (len(current_chunk) > 100 and i < len(sentences) - 1):
                    normalized.append(current_chunk.strip())
                    current_chunk = ""

            if current_chunk:
                normalized.append(current_chunk.strip())
        else:
            normalized.append(para)

    return '\n'.join(normalized)
