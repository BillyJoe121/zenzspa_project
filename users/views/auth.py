"""
Vistas de autenticación: registro, verificación SMS y tokens JWT.
Agrupa exports para mantener compatibilidad con imports existentes.
"""

from .auth_registration import ResendOTPView, UserRegistrationView
from .auth_tokens import CustomTokenObtainPairView, CustomTokenRefreshView
from .auth_user import CurrentUserView, UserDeleteView
from .auth_verification import VerifySMSView

__all__ = [
    "UserRegistrationView",
    "ResendOTPView",
    "VerifySMSView",
    "CustomTokenObtainPairView",
    "CustomTokenRefreshView",
    "CurrentUserView",
    "UserDeleteView",
]
