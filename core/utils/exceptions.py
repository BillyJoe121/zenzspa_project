"""
Core Utils - Exceptions.
"""
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


class InsufficientFundsError(BusinessLogicError):
    """Excepción cuando el usuario no tiene fondos suficientes."""
    default_detail = "Fondos insuficientes para completar la operación."
    default_code = "INSUFFICIENT_FUNDS"


class ResourceConflictError(APIException):
    """Excepción cuando hay un conflicto con el estado actual del recurso."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El recurso está en un estado que no permite esta operación."
    default_code = "RESOURCE_CONFLICT"


class ServiceUnavailableError(APIException):
    """Excepción cuando un servicio externo no está disponible."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "El servicio no está disponible temporalmente."
    default_code = "SERVICE_UNAVAILABLE"


class InvalidStateTransitionError(BusinessLogicError):
    """Excepción cuando se intenta una transición de estado inválida."""
    default_detail = "Transición de estado no permitida."
    default_code = "INVALID_STATE_TRANSITION"
    
    def __init__(self, current_state=None, target_state=None, **kwargs):
        detail = self.default_detail
        extra = kwargs.get('extra', {})
        
        if current_state and target_state:
            detail = f"No se puede cambiar de '{current_state}' a '{target_state}'."
            extra['current_state'] = current_state
            extra['target_state'] = target_state
        
        kwargs['extra'] = extra
        super().__init__(detail=detail, **kwargs)


class RateLimitExceededError(APIException):
    """Excepción cuando se excede el rate limit."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Demasiadas solicitudes. Por favor intenta más tarde."
    default_code = "RATE_LIMIT_EXCEEDED"
    
    def __init__(self, retry_after=None, **kwargs):
        detail = self.default_detail
        if retry_after:
            detail = f"Demasiadas solicitudes. Intenta de nuevo en {retry_after} segundos."
        super().__init__(detail, **kwargs)


class PermissionDeniedError(APIException):
    """Excepción cuando el usuario no tiene permisos."""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No tienes permisos para realizar esta acción."
    default_code = "PERMISSION_DENIED"


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
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }.get(code, "SERVER_ERROR")
