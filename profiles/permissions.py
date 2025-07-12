from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.core.cache import cache
from users.models import CustomUser

class IsStaffOrAdmin(BasePermission):
    """
    Permite el acceso solo a usuarios con rol STAFF o ADMIN.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]

class IsOwnerForReadOrStaff(BasePermission):
    """
    Permiso personalizado que permite:
    - A los dueños del perfil, ver su propio perfil (métodos seguros GET, HEAD, OPTIONS).
    - Al personal (STAFF/ADMIN), realizar cualquier acción.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role in [CustomUser.Role.STAFF, CustomUser.Role.ADMIN]:
            return True
        if obj.user == request.user and request.method in SAFE_METHODS:
            return True
        return False

# --- INICIO DE LA MODIFICACIÓN ---

class IsKioskSession(BasePermission):
    """
    Permiso que valida si la petición se realiza con un token de quiosco válido.
    Adjunta el cliente y el staff asociados a la petición para su uso posterior.
    """
    message = "Sesión de quiosco inválida o expirada."

    def has_permission(self, request, view):
        kiosk_token = request.headers.get('X-Kiosk-Token')
        if not kiosk_token:
            return False

        # Validar el token contra la caché
        session_data = cache.get(f"kiosk_session_{kiosk_token}")
        if not session_data:
            return False

        # Si el token es válido, adjuntamos los datos a la request para usarlos en la vista
        try:
            request.kiosk_client = CustomUser.objects.get(id=session_data['client_id'])
            request.kiosk_staff = CustomUser.objects.get(id=session_data['staff_id'])
            return True
        except CustomUser.DoesNotExist:
            return False
# --- FIN DE LA MODIFICACIÓN ---