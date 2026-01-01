"""
Vistas utilitarias para exponer endpoints simples del núcleo.
"""
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminOrSuperAdmin
from .models import GlobalSettings
from .serializers import GlobalSettingsSerializer, GlobalSettingsUpdateSerializer
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
    Vista API para obtener y actualizar las configuraciones globales del sistema.

    GET: Retorna la configuración global completa serializada.
         Los campos sensibles (comisiones del desarrollador) solo son
         visibles para usuarios con rol ADMIN.

    PATCH: Actualiza la configuración global.
           Restringido a usuarios con rol ADMIN o SuperAdmin.

    Requiere autenticación.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT"]:
            return [IsAuthenticated(), IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]

    def get(self, request, *args, **kwargs):
        """
        Obtiene y serializa la configuración global del sistema.

        Returns:
            Response: Configuración global serializada según el rol del usuario.
        """
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        """
        Actualiza parcialmente la configuración global.
        """
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsUpdateSerializer(
            settings_obj,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # IMPORTANTE: Recargar desde caché actualizado para devolver valores frescos
        settings_obj = GlobalSettings.load()

        # Retornamos la representación completa actualizada
        response_serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)
