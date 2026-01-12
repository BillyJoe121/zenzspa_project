"""
Configuración de URLs para el módulo core.

Define los endpoints principales del núcleo del sistema:
- /health/: Health check para monitoreo (sin autenticación)
- /settings/: Configuraciones globales del sistema (CRUD, requiere autenticación)
- /about/: Página "Quiénes Somos" (público para lectura, ADMIN para escritura)
- /team-members/: Miembros del equipo (público para lectura, ADMIN para escritura)
- /gallery-images/: Galería de imágenes (público para lectura, ADMIN para escritura)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from core.api.views import (
    HealthCheckView, 
    GlobalSettingsView
)
from core.api.viewsets import (
    GlobalSettingsViewSet,
    AboutPageViewSet,
    TeamMemberViewSet,
    GalleryImageViewSet,
)

router = DefaultRouter()
# router.register(r'settings', GlobalSettingsViewSet, basename='settings') # Replaced by GlobalSettingsView
router.register(r'about', AboutPageViewSet, basename='about')
router.register(r'team-members', TeamMemberViewSet, basename='team-member')
router.register(r'gallery-images', GalleryImageViewSet, basename='gallery-image')

urlpatterns = [
    # Health check para load balancers y monitoreo
    path("health/", HealthCheckView.as_view(), name="health"),
    
    # Singleton endpoint for Global Settings
    path("settings/", GlobalSettingsView.as_view(), name="global-settings"),

    # Router para ViewSets
    path('', include(router.urls)),
]
