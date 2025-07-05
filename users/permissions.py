# Reemplaza todo el contenido de zenzspa_project/users/permissions.py

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
