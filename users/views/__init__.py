"""
Módulo de vistas de usuarios.

Exporta todas las vistas para mantener compatibilidad con imports existentes.
"""
from .admin_views import (
    AdminUserViewSet,
    BlockIPView,
    FlagNonGrataView,
    StaffListView,
    UserExportView,
)
from .auth import (
    CurrentUserView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    UserRegistrationView,
    VerifySMSView,
    UserDeleteView,
)
from .password import (
    ChangePasswordView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
)
from .sessions import (
    LogoutAllView,
    LogoutView,
    UserSessionDeleteView,
    UserSessionListView,
)
from .totp import TOTPSetupView, TOTPVerifyView
from .webhooks import EmailVerificationView, TwilioWebhookView

# Importar servicios y utilidades para compatibilidad con tests legacy
from ..services import TwilioService, verify_recaptcha
from .utils import requires_recaptcha, revoke_all_sessions

# Imports de otros módulos para compatibilidad con tests
from spa.models import Appointment
from core.models import AuditLog, AdminNotification
from notifications.services import NotificationService

# Aliases para compatibilidad con tests que usan nombres con guion bajo
_requires_recaptcha = requires_recaptcha
_revoke_all_sessions = revoke_all_sessions

__all__ = [
    # Auth
    'UserRegistrationView',
    'VerifySMSView',
    'CustomTokenObtainPairView',
    'CustomTokenRefreshView',
    'CurrentUserView',
    'UserDeleteView',
    # Password
    'PasswordResetRequestView',
    'PasswordResetConfirmView',
    'ChangePasswordView',
    # Sessions
    'LogoutView',
    'LogoutAllView',
    'UserSessionListView',
    'UserSessionDeleteView',
    # TOTP
    'TOTPSetupView',
    'TOTPVerifyView',
    # Admin
    'FlagNonGrataView',
    'StaffListView',
    'BlockIPView',
    'AdminUserViewSet',
    'UserExportView',
    # Webhooks
    'TwilioWebhookView',
    'EmailVerificationView',
    # Services (for backward compatibility with tests)
    'TwilioService',
    'verify_recaptcha',
    'requires_recaptcha',
    '_requires_recaptcha',
    'revoke_all_sessions',
    '_revoke_all_sessions',
    # Models and services from other modules (for test patches)
    'Appointment',
    'AuditLog',
    'AdminNotification',
    'NotificationService',
]
