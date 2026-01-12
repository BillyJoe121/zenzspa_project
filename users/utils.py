from typing import Optional, Tuple

from django.http import HttpRequest


def get_client_ip(request: Optional[HttpRequest]) -> Optional[str]:
    """
    Obtiene la IP del cliente tomando en cuenta proxies (X-Forwarded-For).
    """
    if request is None:
        return None

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_request_metadata(request: Optional[HttpRequest]) -> Tuple[Optional[str], str]:
    """
    Retorna (ip, user_agent) asegurando un máximo de 512 chars para UA.
    """
    ip = get_client_ip(request)
    user_agent = ""
    if request is not None:
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]
    return ip, user_agent


def register_user_session(user, refresh_token_jti: str, request: Optional[HttpRequest] = None,
                          ip_address: Optional[str] = None, user_agent: Optional[str] = None,
                          sender=None) -> None:
    """
    Dispara la señal user_session_logged_in centralizando obtención de metadata.
    """
    from .signals import user_session_logged_in  # Import diferido para evitar ciclos

    resolved_ip = ip_address if ip_address is not None else get_client_ip(request)
    resolved_agent = user_agent if user_agent is not None else ("" if request is None else request.META.get("HTTP_USER_AGENT", ""))
    user_session_logged_in.send(
        sender=sender or __name__,
        user=user,
        refresh_token_jti=refresh_token_jti,
        ip_address=resolved_ip,
        user_agent=(resolved_agent or "")[:512],
    )
