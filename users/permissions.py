from rest_framework.permissions import BasePermission
from .models import CustomUser

class IsVerified(BasePermission):
    """
    Permiso personalizado para permitir el acceso solo a usuarios verificados.
    """
    message = 'Tu cuenta no ha sido verificada. Por favor, completa la verificación por SMS.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_verified

# --- INICIO DE LA MODIFICACIÓN ---

class IsClient(BasePermission):
    """Permite el acceso solo a usuarios con rol CLIENT."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == CustomUser.Role.CLIENT

class IsVIP(BasePermission):
    """Permite el acceso solo a usuarios con rol VIP."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == CustomUser.Role.VIP

class IsStaff(BasePermission):
    """Permite el acceso solo a usuarios con rol STAFF."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == CustomUser.Role.STAFF

class IsSuperAdmin(BasePermission):
    """
    Permite el acceso SOLO a superusuarios (is_superuser=True).
    Los superadmins tienen control total sobre todos los usuarios, incluyendo otros admins.
    """
    message = 'Esta acción requiere permisos de superadministrador.'
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.is_superuser
        )

class IsAdminUser(BasePermission):
    """
    Permite el acceso a usuarios con rol ADMIN (incluyendo superadmins).
    Nota: Para acciones sensibles sobre otros admins, usa IsSuperAdmin.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.role == CustomUser.Role.ADMIN
        )

class IsAdminOrSuperAdmin(BasePermission):
    """Permite el acceso a administradores o superadministradores."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            (request.user.role == CustomUser.Role.ADMIN or request.user.is_superuser)
        )

class IsStaffOrAdmin(BasePermission):
    """Permite el acceso a usuarios con rol STAFF o ADMIN."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]

# --- FIN DE LA MODIFICACIÓN ---