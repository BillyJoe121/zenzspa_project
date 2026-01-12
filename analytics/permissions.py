from rest_framework import permissions
from users.models import CustomUser


class CanViewAnalytics(permissions.BasePermission):
    """
    Permite acceso solo a administradores y staff autorizado.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admins siempre tienen acceso
        if request.user.role == CustomUser.Role.ADMIN:
            return True
            
        # Staff solo si tiene permiso explícito (futuro) o es staff
        # Por ahora mantenemos compatibilidad con IsStaffOrAdmin pero encapsulado
        if request.user.is_staff or request.user.role == CustomUser.Role.STAFF:
            return True
            
        return False


class CanViewFinancialMetrics(permissions.BasePermission):
    """
    Permite acceso a métricas financieras sensibles SOLO a administradores.
    Incluye: ingresos, deuda, LTV, AOV, growth rates.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        return request.user.role == CustomUser.Role.ADMIN


class CanViewOperationalMetrics(permissions.BasePermission):
    """
    Permite acceso a métricas operativas a administradores y staff.
    Incluye: heatmap, leaderboard, funnel, waitlist.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        return request.user.role in [
            CustomUser.Role.ADMIN,
            CustomUser.Role.STAFF
        ]
