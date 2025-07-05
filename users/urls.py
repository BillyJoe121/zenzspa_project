from django.urls import path
from .views import (
    UserRegistrationView,
    VerifySMSView,
    CustomTokenObtainPairView,
    CurrentUserView,
    FlagNonGrataView,
    PasswordResetRequestView,    # <-- Importado
    PasswordResetConfirmView,
    StaffListView   # <-- Importado
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # --- Autenticación y Registro ---
    path('register/', UserRegistrationView.as_view(), name='user_register'),
    path('verify-sms/', VerifySMSView.as_view(), name='verify_sms'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # --- Reseteo de Contraseña ---
    path('password-reset/request/', PasswordResetRequestView.as_view(),
         name='password_reset_request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),

    # --- Gestión de Usuario ---
    path('me/', CurrentUserView.as_view(), name='current_user'),
    path('admin/flag-non-grata/<str:phone_number>/',
         FlagNonGrataView.as_view(), name='flag_non_grata'),

     path('staff/', StaffListView.as_view(), name='staff-list'),

]
