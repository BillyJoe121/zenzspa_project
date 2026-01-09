"""
Core API - Routers.
"""
from rest_framework.routers import DefaultRouter


def get_default_router() -> DefaultRouter:
    """
    Crea y retorna un router DRF con configuración estándar.

    El router devuelto está configurado con:
    - trailing_slash=True: URLs terminan con '/' (estándar de Django)

    Returns:
        DefaultRouter: Router configurado para registro de ViewSets.

    Uso:
        router = get_default_router()
        router.register(r'users', UserViewSet)
        urlpatterns = router.urls
    """
    return DefaultRouter(trailing_slash=True)
