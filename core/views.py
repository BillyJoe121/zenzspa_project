"""
Vistas utilitarias para exponer endpoints simples del núcleo.
"""
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from .models import GlobalSettings


class HealthCheckView(View):
    """
    Endpoint ligero para verificar que la aplicación puede leer
    configuración crítica y responder peticiones básicas.

    Responde con la hora actual y la zona configurada para facilitar
    la observabilidad desde load balancers o servicios de monitoreo.
    """

    http_method_names = ["get", "head", "options", "trace"]

    def get(self, request, *args, **kwargs):
        settings_obj = GlobalSettings.load()
        payload = {
            "status": "ok",
            "timestamp": timezone.now().isoformat(),
            "timezone": settings_obj.timezone_display,
        }
        return JsonResponse(payload, status=200)
