from django.urls import path
from .views import (
    UserRegistrationView,
    VerifySMSView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CurrentUserView,
    FlagNonGrataView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    StaffListView,
    UserSessionListView,
    UserSessionDeleteView,
    LogoutView,
    LogoutAllView,
)


urlpatterns = [
    # OTP + Session flows
    path('otp/request/', UserRegistrationView.as_view(), name='otp-request'),
    path('otp/confirm/', VerifySMSView.as_view(), name='otp-confirm'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout_all/', LogoutAllView.as_view(), name='logout_all'),

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
]
