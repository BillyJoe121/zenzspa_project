from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessLogicError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Regla de negocio no satisfecha."
    default_code = "BUSINESS_LOGIC_ERROR"

    def __init__(self, detail=None, *, internal_code=None, status_code=None, extra=None):
        payload = {"detail": detail or self.default_detail}
        if internal_code:
            payload["code"] = internal_code
        if extra:
            payload["meta"] = extra
        if status_code:
            self.status_code = status_code
        super().__init__(payload, self.default_code)


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
        if "code" in response.data:
            normalized["code"] = response.data.get("code")
        extra = {k: v for k, v in response.data.items() if k not in {"detail", "code"}}
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
