"""
Core API - Permissions.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS
import logging

logger = logging.getLogger(__name__)


class IsAuthenticatedAndActive(BasePermission):
    message = "Autenticación requerida."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)


class IsAdmin(BasePermission):
    message = "Se requieren permisos de administrador."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, "role", "") == "ADMIN")


class IsStaff(BasePermission):
    message = "Se requieren permisos de staff."

    def has_permission(self, request, view):
        role = getattr(request.user, "role", "")
        return bool(request.user and request.user.is_authenticated and role in {"STAFF", "ADMIN"})


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class RoleAllowed(BasePermission):
    """
    Usa en la vista: required_roles = {"CLIENT","VIP","STAFF","ADMIN"}
    """
    message = "Tu rol no está autorizado para esta operación."
    
    VALID_ROLES = {"CLIENT", "VIP", "STAFF", "ADMIN"}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        required = getattr(view, "required_roles", None)
        if not required:
            return True
        
        # Validar que required_roles contenga roles válidos
        if not isinstance(required, (set, list, tuple)):
            logger.error(
                "required_roles debe ser un set/list/tuple, recibido: %s",
                type(required)
            )
            return False
        
        invalid_roles = set(required) - self.VALID_ROLES
        if invalid_roles:
            logger.error(
                "Roles inválidos en required_roles: %s",
                invalid_roles
            )
            return False
        
        role = getattr(request.user, "role", None)
        return role in required
