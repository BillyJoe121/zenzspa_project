import uuid
import time
import logging
from dataclasses import dataclass
from typing import Optional

from django.utils.deprecation import MiddlewareMixin
from django.utils.timezone import now
from django.conf import settings
from django.http import HttpRequest

from .utils import get_client_ip, safe_audit_log

logger = logging.getLogger(__name__)

_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
_RESPONSE_ID_HEADER = "X-Request-ID"

@dataclass
class RequestMeta:
    id: str
    ip: str
    path: str
    method: str
    user_id: Optional[str]


class RequestIDMiddleware(MiddlewareMixin):
    """
    Inyecta un X-Request-ID para trazar peticiones en logs/errores.
    """
    def process_request(self, request):
        rid = request.META.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.request_id = rid
        return None

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response[_RESPONSE_ID_HEADER] = rid
        return response


class AdminAuditMiddleware(MiddlewareMixin):
    """
    Registra acciones sensibles en AuditLog cuando el path coincide con rutas /api/v1/admin/.
    No interfiere con el flujo si AuditLog falla: tolerante a errores.
    """
    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        # Solo observar, registrar al final si status es 2xx/4xx
        request._audit_meta = RequestMeta(
            id=getattr(request, "request_id", str(uuid.uuid4())),
            ip=get_client_ip(request),
            path=request.path,
            method=request.method,
            user_id=str(getattr(getattr(request, "user", None), "id", "")) or None,
        )
        return None

    def process_response(self, request, response):
        try:
            if request.path.startswith("/api/v1/admin/") and getattr(request, "user", None) and request.user.is_authenticated:
                details = {
                    "request_id": getattr(request, "request_id", None),
                    "ip": getattr(request, "_audit_meta", None).ip if hasattr(request, "_audit_meta") else None,
                    "status_code": response.status_code,
                    "at": now().isoformat(),
                }
                # No intentamos inferir target_user/appointment aquí.
                safe_audit_log(
                    action="ADMIN_ENDPOINT_HIT",
                    admin_user=request.user,
                    details=details,
                )
        except Exception:
            # Nada de romper la cadena por auditar.
            if getattr(settings, "DEBUG", False):
                raise
        return response


class PerformanceLoggingMiddleware(MiddlewareMixin):
    """
    Middleware para loggear tiempos de respuesta y detectar endpoints lentos.
    
    Configuración en settings.py:
        SLOW_REQUEST_THRESHOLD = 1.0  # segundos
    """
    
    def process_request(self, request):
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        if not hasattr(request, '_start_time'):
            return response
        
        duration = time.time() - request._start_time
        
        # Threshold configurable (default: 1 segundo)
        slow_threshold = getattr(settings, 'SLOW_REQUEST_THRESHOLD', 1.0)
        
        # Loggear requests lentos
        if duration > slow_threshold:
            logger.warning(
                "Slow request detected: %s %s - %.2fs",
                request.method,
                request.path,
                duration,
                extra={
                    'request_id': getattr(request, 'request_id', None),
                    'duration': duration,
                    'path': request.path,
                    'method': request.method,
                    'status_code': response.status_code,
                    'user_id': str(request.user.id) if hasattr(request, 'user') and request.user.is_authenticated else None,
                }
            )
        
        # Agregar header con tiempo de respuesta
        response['X-Response-Time'] = f"{duration:.3f}s"
        
        return response
    
    def process_exception(self, request, exception):
        """Loggear también cuando hay excepciones"""
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            logger.error(
                "Request failed: %s %s - %.2fs - %s",
                request.method,
                request.path,
                duration,
                str(exception),
                extra={
                    'request_id': getattr(request, 'request_id', None),
                    'duration': duration,
                    'exception': str(exception),
                }
            )
        return None
