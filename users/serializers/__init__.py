"""
Serializers del módulo users.
Este archivo actúa como contenedor para mantener compatibilidad con imports existentes.
"""

from ..services import verify_recaptcha
from ..tasks import send_non_grata_alert_to_admins
from ..utils import register_user_session
from .export import UserExportSerializer
from .security import (
    FlagNonGrataSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    StaffListSerializer,
    UserSessionSerializer,
    VerifySMSSerializer,
)
from .tokens import (
    CustomTokenObtainPairSerializer,
    SessionAwareTokenRefreshSerializer,
)
from .totp import TOTPSetupSerializer, TOTPVerifySerializer
from .user import (
    AdminUserSerializer,
    SimpleUserSerializer,
    UserRegistrationSerializer,
)

__all__ = [
    "CustomTokenObtainPairSerializer",
    "SessionAwareTokenRefreshSerializer",
    "SimpleUserSerializer",
    "UserRegistrationSerializer",
    "AdminUserSerializer",
    "VerifySMSSerializer",
    "PasswordResetRequestSerializer",
    "PasswordResetConfirmSerializer",
    "FlagNonGrataSerializer",
    "StaffListSerializer",
    "UserSessionSerializer",
    "TOTPSetupSerializer",
    "TOTPVerifySerializer",
    "UserExportSerializer",
    "send_non_grata_alert_to_admins",
    "verify_recaptcha",
    "register_user_session",
]
