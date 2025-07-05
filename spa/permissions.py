from rest_framework import permissions
from users.models import CustomUser

# Permiso existente


class IsAdminOrOwnerOfAvailability(permissions.BasePermission):
    """
    Permite acceso a los admins, o al staff si son dueños del objeto.
    """

    def has_object_permission(self, request, view, obj):
        # El admin siempre tiene permiso
        if request.user.role == CustomUser.Role.ADMIN:
            return True
        # El staff solo si el objeto le pertenece
        return obj.staff_member == request.user

# --- PERMISO AÑADIDO ---


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permiso personalizado para permitir acceso de solo lectura a cualquiera,
    pero solo permitir operaciones de escritura (POST, PUT, PATCH, DELETE) a los administradores.
    """

    def has_permission(self, request, view):
        # Permite métodos seguros (GET, HEAD, OPTIONS) a cualquier petición.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Para métodos no seguros, solo permite si el usuario está autenticado y es ADMIN.
        return request.user and request.user.is_authenticated and request.user.role == CustomUser.Role.ADMIN
