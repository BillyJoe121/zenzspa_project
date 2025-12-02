"""
Vistas utilitarias para exponer endpoints simples del núcleo.
"""
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GlobalSettings
from .serializers import GlobalSettingsSerializer
from django.shortcuts import render


class HealthCheckView(View):
    """
    Endpoint ligero para verificar que la aplicación puede leer
    configuración crítica y responder peticiones básicas.

    Responde con la hora actual y la zona configurada para facilitar
    la observabilidad desde load balancers o servicios de monitoreo.

    No requiere autenticación y devuelve información mínima.
    Para configuraciones completas, usar GlobalSettingsView.
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


class GlobalSettingsView(APIView):
    """
    Vista API para obtener todas las configuraciones globales del sistema.

    GET: Retorna la configuración global completa serializada.
         Los campos sensibles (comisiones del desarrollador) solo son
         visibles para usuarios con rol ADMIN.

    Requiere autenticación. Los campos visibles dependen del rol del usuario.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        """
        Obtiene y serializa la configuración global del sistema.

        Returns:
            Response: Configuración global serializada según el rol del usuario.
        """
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(serializer.data)
