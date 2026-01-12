from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    ChangePasswordView,
    UserRegistrationView,
    ResendOTPView,
    VerifySMSView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CurrentUserView,
    FlagNonGrataView,
    BlockIPView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    StaffListView,
    UserSessionListView,
    UserSessionDeleteView,
    LogoutView,
    LogoutAllView,
    TOTPSetupView,
    TOTPVerifyView,
    UserExportView,
    TwilioWebhookView,
    EmailVerificationView,
    UserDeleteView,
    AdminUserViewSet,
)

router = DefaultRouter()
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')



urlpatterns = [
    # OTP + Session flows
    path('admin/export/', UserExportView.as_view(), name='user-export'),
    path('otp/request/', UserRegistrationView.as_view(), name='otp-request'),
    path('otp/resend/', ResendOTPView.as_view(), name='otp-resend'),
    path('otp/confirm/', VerifySMSView.as_view(), name='otp-confirm'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout_all/', LogoutAllView.as_view(), name='logout_all'),
    path('password/change/', ChangePasswordView.as_view(), name='password_change'),
    path('admin/block-ip/', BlockIPView.as_view(), name='block_ip'),

    # Password management
    path(
        'password-reset/request/',
        PasswordResetRequestView.as_view(),
        name='password_reset_request',
    ),
    path(
        'password-reset/confirm/',
        PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),

    # User profile helpers
    path('me/', CurrentUserView.as_view(), name='current_user'),
    path(
        'admin/flag-non-grata/<str:phone_number>/',
        FlagNonGrataView.as_view(),
        name='flag_non_grata',
    ),
    path('staff/', StaffListView.as_view(), name='staff-list'),
    path('sessions/', UserSessionListView.as_view(), name='session-list'),
    path('sessions/<uuid:id>/', UserSessionDeleteView.as_view(), name='session-delete'),

    # New Features
    path('totp/setup/', TOTPSetupView.as_view(), name='totp-setup'),
    path('totp/verify/', TOTPVerifyView.as_view(), name='totp-verify'),
    path('twilio/webhook/', TwilioWebhookView.as_view(), name='twilio-webhook'),
    path('email/verify/', EmailVerificationView.as_view(), name='email-verify'),
    path('me/delete/', UserDeleteView.as_view(), name='user-delete'),

    # Rutas administrativas (router)
    path('', include(router.urls)),
]
