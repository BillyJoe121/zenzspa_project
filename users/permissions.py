from rest_framework.permissions import BasePermission
from .models import CustomUser


class IsAdminUser(BasePermission):
    """
    Permite el acceso solo a usuarios con rol ADMIN.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == CustomUser.Role.ADMIN


class IsVerified(BasePermission):
    """
    Permiso personalizado para permitir el acceso solo a usuarios verificados.
    """
    message = 'Tu cuenta no ha sido verificada. Por favor, completa la verificación por SMS.'

    def has_permission(self, request, view):
        # El permiso solo se aplica a usuarios autenticados.
        if not request.user or not request.user.is_authenticated:
            return False
        # Devuelve True si el usuario tiene el campo is_verified en True.
        return request.user.is_verified