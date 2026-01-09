"""
Core API - Throttling.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class BurstAnonThrottle(AnonRateThrottle):
    """Rate limit para ráfagas de usuarios anónimos."""
    scope = "burst_anon"   # REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['burst_anon'] = '20/min'


class SustainedAnonThrottle(AnonRateThrottle):
    """Rate limit sostenido para usuarios anónimos."""
    scope = "sustained_anon"  # '200/hour'


class BurstUserThrottle(UserRateThrottle):
    """Rate limit para ráfagas de usuarios autenticados."""
    scope = "burst_user"   # '60/min'


class LoginThrottle(AnonRateThrottle):
    """Rate limit restrictivo para intentos de login."""
    scope = "login"        # '5/min'


class PasswordChangeThrottle(UserRateThrottle):
    """
    Rate limit restrictivo para cambios de contraseña.

    Protege contra ataques de fuerza bruta donde un atacante
    que haya comprometido una sesión intente cambiar la contraseña
    repetidamente.
    """
    scope = "password_change"  # '3/hour'

class AdminThrottle(UserRateThrottle):
    scope = "admin"  # '1000/hour' en settings
    
    def allow_request(self, request, view):
        # Solo aplicar a usuarios admin
        if not request.user or not request.user.is_authenticated:
            return True
        
        if getattr(request.user, 'role', '') != 'ADMIN':
            return True
        
        return super().allow_request(request, view)
