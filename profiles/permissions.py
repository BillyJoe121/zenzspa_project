from rest_framework.permissions import BasePermission, SAFE_METHODS
from users.models import CustomUser
from users.permissions import IsStaffOrAdmin # Se mantiene la importación, es correcta.
from django.core.cache import cache # Se añade la importación de cache que faltaba en tu archivo original

class ClinicalProfileAccessPermission(BasePermission):
    """
    Permisos granulares para el Perfil Clínico, cumpliendo con RFD-CLI-02.
    - El dueño del perfil (CLIENT/VIP) solo puede verlo (Read-Only).
    - El personal (STAFF) puede ver y actualizar cualquier perfil, pero no eliminar.
    - El administrador (ADMIN) tiene permisos totales (incluyendo DELETE).
    """

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role == user.Role.ADMIN:
            return True

        if user.role == user.Role.STAFF:
            if request.method == 'DELETE':
                return False
            return True

        if user.role in [user.Role.CLIENT, user.Role.VIP]:
            if obj.user == user:
                return request.method in SAFE_METHODS
            return False
        
        return False
# --- FIN DE LA MODIFICACIÓN ---


class IsOwnerForReadOrStaff(BasePermission):
    """
    Permiso existente. Se mantiene sin cambios para no afectar otras funcionalidades.
    """
    def has_object_permission(self, request, view, obj):
        if IsStaffOrAdmin().has_permission(request, view):
            return True

        if obj.user == request.user and request.method in SAFE_METHODS:
            return True

        return False

class IsKioskSession(BasePermission):
    """
    Permiso existente para el Modo Quiosco. Se mantiene sin cambios.
    """
    message = "Sesión de quiosco inválida o expirada."

    def has_permission(self, request, view):
        kiosk_token = request.headers.get('X-Kiosk-Token')
        if not kiosk_token:
            return False

        session_data = cache.get(f"kiosk_session_{kiosk_token}")
        if not session_data:
            return False

        try:
            request.kiosk_client = CustomUser.objects.get(id=session_data['client_id'])
            request.kiosk_staff = CustomUser.objects.get(id=session_data['staff_id'])
            return True
        except CustomUser.DoesNotExist:
            return False
        
class IsVerifiedUserOrKioskSession(BasePermission):
    """
    Permite el acceso si el usuario está autenticado y verificado
    O si la petición se realiza a través de una sesión de quiosco válida.
    """
    def has_permission(self, request, view):
        # DRF permite componer permisos usando operadores lógicos.
        # La siguiente línea es equivalente a: return IsVerified().check() OR IsKioskSession().check()
        return IsVerified().has_permission(request, view) or IsKioskSession().has_permission(request, view)
