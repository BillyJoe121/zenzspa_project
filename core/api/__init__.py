"""
Paquete API de Core.

Contiene toda la infraestructura DRF: vistas, viewsets, permisos, paginación, throttling, routers.

Exporta:
- Views: HealthCheckView, GlobalSettingsView
- ViewSets: GlobalSettingsViewSet, AboutPageViewSet, TeamMemberViewSet, GalleryImageViewSet
- Permissions: IsAuthenticatedAndActive, IsAdmin, IsStaff, ReadOnly, RoleAllowed
- Pagination: DefaultPageNumberPagination
- Throttling: BurstAnonThrottle, SustainedAnonThrottle, BurstUserThrottle, LoginThrottle, PasswordChangeThrottle, AdminThrottle
- Routers: get_default_router
"""
from core.api.views import HealthCheckView, GlobalSettingsView
from core.api.viewsets import (
    GlobalSettingsViewSet,
    AboutPageViewSet,
    TeamMemberViewSet,
    GalleryImageViewSet,
)
from core.api.permissions import (
    IsAuthenticatedAndActive,
    IsAdmin,
    IsStaff,
    ReadOnly,
    RoleAllowed,
)
from core.api.pagination import DefaultPageNumberPagination
from core.api.throttling import (
    BurstAnonThrottle,
    SustainedAnonThrottle,
    BurstUserThrottle,
    LoginThrottle,
    PasswordChangeThrottle,
    AdminThrottle,
)
from core.api.routers import get_default_router


__all__ = [
    # Views
    "HealthCheckView",
    "GlobalSettingsView",
    # ViewSets
    "GlobalSettingsViewSet",
    "AboutPageViewSet",
    "TeamMemberViewSet",
    "GalleryImageViewSet",
    # Permissions
    "IsAuthenticatedAndActive",
    "IsAdmin",
    "IsStaff",
    "ReadOnly",
    "RoleAllowed",
    # Pagination
    "DefaultPageNumberPagination",
    # Throttling
    "BurstAnonThrottle",
    "SustainedAnonThrottle",
    "BurstUserThrottle",
    "LoginThrottle",
    "PasswordChangeThrottle",
    "AdminThrottle",
    # Routers
    "get_default_router",
]
