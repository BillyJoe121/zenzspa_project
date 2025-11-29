"""
Configuración de URLs para el módulo core.

Define los endpoints principales del núcleo del sistema:
- /health/: Health check para monitoreo (sin autenticación)
- /settings/: Configuraciones globales del sistema (requiere autenticación)
"""
from django.urls import path

from .views import GlobalSettingsView, HealthCheckView

app_name = "core"

urlpatterns = [
    # Health check para load balancers y monitoreo
    path("health/", HealthCheckView.as_view(), name="health"),

    # Configuraciones globales del sistema
    path("settings/", GlobalSettingsView.as_view(), name="global-settings"),
]
