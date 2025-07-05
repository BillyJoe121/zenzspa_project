# Crea el archivo zenzspa_project/profiles/permissions.py con este contenido

from rest_framework.permissions import BasePermission
from users.models import CustomUser


class IsStaffOrAdmin(BasePermission):
    """
    Permite el acceso solo a usuarios con rol STAFF o ADMIN.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]
