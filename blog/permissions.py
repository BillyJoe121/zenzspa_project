from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permiso personalizado que permite:
    - Lectura (GET, HEAD, OPTIONS) a cualquiera
    - Escritura (POST, PUT, PATCH, DELETE) solo a administradores
    """

    def has_permission(self, request, view):
        # Permitir métodos de lectura a todos
        if request.method in permissions.SAFE_METHODS:
            return True

        # Permitir escritura solo a staff/admin autenticados
        return request.user and request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # Permitir métodos de lectura a todos
        if request.method in permissions.SAFE_METHODS:
            return True

        # Permitir escritura solo a staff/admin autenticados
        return request.user and request.user.is_authenticated and request.user.is_staff
