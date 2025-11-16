from rest_framework.permissions import BasePermission, SAFE_METHODS
from users.models import CustomUser
from users.permissions import IsStaffOrAdmin, IsVerified  # Se mantiene la importación, es correcta.
from .models import KioskSession

class ClinicalProfileAccessPermission(BasePermission):
    """
    Permisos granulares para el Perfil Clínico, cumpliendo con RFD-CLI-02.
    - El dueño del perfil (CLIENT/VIP) solo puede verlo (Read-Only).
    - El personal (STAFF) puede ver y actualizar cualquier perfil, pero no eliminar.
    - El administrador (ADMIN) tiene permisos totales (incluyendo DELETE).
    """

    def has_object_permission(self, request, view, obj):
        user = getattr(request, 'user', None)

        kiosk_client = getattr(request, 'kiosk_client', None)
        if kiosk_client and obj.user == kiosk_client:
            return True

        if not user or not getattr(user, 'is_authenticated', False):
            return False

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
        session = load_kiosk_session_from_request(request, attach=True)
        return session is not None
        
class IsVerifiedUserOrKioskSession(BasePermission):
    """
    Permite el acceso si el usuario está autenticado y verificado
    O si la petición se realiza a través de una sesión de quiosco válida.
    """
    def has_permission(self, request, view):
        # DRF permite componer permisos usando operadores lógicos.
        # La siguiente línea es equivalente a: return IsVerified().check() OR IsKioskSession().check()
        return IsVerified().has_permission(request, view) or IsKioskSession().has_permission(request, view)


def load_kiosk_session_from_request(request, *, allow_inactive=False, attach=False):
    kiosk_token = request.headers.get('X-Kiosk-Token')
    if not kiosk_token:
        return None

    try:
        session = KioskSession.objects.select_related(
            'profile__user',
            'staff_member',
        ).get(token=kiosk_token)
    except KioskSession.DoesNotExist:
        return None

    if session.has_expired:
        session.mark_expired()

    if not allow_inactive and not session.is_valid:
        return None

    if session.is_valid:
        session.heartbeat()

    if attach:
        request.kiosk_client = session.profile.user
        request.kiosk_staff = session.staff_member
        request.kiosk_session = session
    return session
