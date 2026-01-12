from django.conf import settings
from django.http import JsonResponse

from .permissions import load_kiosk_session_from_request


class KioskFlowEnforcementMiddleware:
    """
    Bloquea la navegación fuera del flujo permitido cuando la petición proviene
    de una sesión de quiosco.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_prefixes = tuple(getattr(settings, "KIOSK_ALLOWED_PATH_PREFIXES", ()))
        self.allowed_view_names = set(getattr(settings, "KIOSK_ALLOWED_VIEW_NAMES", ()))

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        kiosk_token = request.headers.get("X-Kiosk-Token")
        if not kiosk_token:
            return None

        resolver_match = getattr(request, "resolver_match", None)
        path = request.path or ""

        if self._is_path_allowed(path, resolver_match):
            return None

        session = load_kiosk_session_from_request(request, allow_inactive=True, attach=False)
        if session and session.is_valid:
            session.lock()

        response_data = {
            "detail": "Navegación bloqueada para sesiones de quiosco.",
            "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
        }
        return JsonResponse(response_data, status=403)

    def _is_path_allowed(self, path, resolver_match):
        if self.allowed_prefixes and path.startswith(self.allowed_prefixes):
            return True
        if resolver_match:
            view_name = resolver_match.view_name
            if view_name and view_name in self.allowed_view_names:
                return True
        return False
