from rest_framework.views import exception_handler
from rest_framework import status

def drf_exception_handler(exc, context):
    """
    Normaliza errores según tu convención (400/401/403/404/409/422/429/5xx).
    """
    response = exception_handler(exc, context)

    if response is None:
        # Error inesperado
        return None

    default_detail = response.data.get("detail") if isinstance(response.data, dict) else None
    code = response.status_code

    normalized = {
        "status_code": code,
        "error": _map_http_to_code(code),
        "detail": default_detail or "Error",
    }
    # Adjunta errores de validación detallados si existen
    if isinstance(response.data, dict):
        extra = {k: v for k, v in response.data.items() if k != "detail"}
        if extra:
            normalized["errors"] = extra

    response.data = normalized
    return response

def _map_http_to_code(code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
        status.HTTP_401_UNAUTHORIZED: "NOT_AUTHENTICATED",
        status.HTTP_403_FORBIDDEN: "NOT_AUTHORIZED",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "BUSINESS_RULE_VIOLATION",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
    }.get(code, "SERVER_ERROR")
