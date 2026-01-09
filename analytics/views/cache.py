"""
Views Cache - Limpieza de caché de Analytics.
"""
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin

from analytics.views.shared import audit_analytics


class CacheClearView(APIView):
    """
    Endpoint para limpiar el caché de analytics.
    Solo accesible para admins.
    """
    permission_classes = [IsStaffOrAdmin]

    def post(self, request):
        """
        Limpia el caché de analytics.
        Parámetros opcionales:
        - scope: 'kpis', 'timeseries', 'dashboard', 'all' (default: 'all')
        """
        scope = request.data.get('scope', 'all')

        if scope not in ['kpis', 'timeseries', 'dashboard', 'dataset', 'all']:
            return Response(
                {"error": "Scope inválido. Use: kpis, timeseries, dashboard, dataset, o all"},
                status=400
            )

        cleared_count = 0

        try:
            if scope == 'all':
                # Limpiar todas las claves que empiecen con 'analytics:'
                # Nota: Esto requiere acceso al backend de caché
                from django.core.cache import cache as django_cache

                # Para Redis, podemos usar keys()
                if hasattr(django_cache, 'keys'):
                    keys = django_cache.keys('analytics:*')
                    for key in keys:
                        django_cache.delete(key)
                        cleared_count += 1
                else:
                    # Fallback: limpiar todo el caché
                    django_cache.clear()
                    cleared_count = -1  # Indicador de limpieza total

            else:
                # Limpiar solo el scope específico
                from django.core.cache import cache as django_cache

                if hasattr(django_cache, 'keys'):
                    pattern = f'analytics:{scope}:*'
                    keys = django_cache.keys(pattern)
                    for key in keys:
                        django_cache.delete(key)
                        cleared_count += 1
                else:
                    return Response(
                        {"error": "El backend de caché no soporta limpieza selectiva. Use scope='all'"},
                        status=400
                    )

            audit_analytics(
                request,
                "cache_cleared",
                {"scope": scope, "cleared_count": cleared_count}
            )

            message = f"Caché limpiado exitosamente"
            if cleared_count >= 0:
                message += f": {cleared_count} claves eliminadas"

            return Response({
                "success": True,
                "message": message,
                "scope": scope,
                "cleared_count": cleared_count if cleared_count >= 0 else "all"
            })

        except Exception as e:
            return Response(
                {"error": f"Error limpiando caché: {str(e)}"},
                status=500
            )
