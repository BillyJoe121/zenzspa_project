"""
Vistas para obtención y refresco de tokens JWT.
"""
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from ..serializers import (
    CustomTokenObtainPairSerializer,
    SessionAwareTokenRefreshSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Vista personalizada para obtener tokens JWT."""

    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """Vista personalizada para refrescar tokens JWT."""

    serializer_class = SessionAwareTokenRefreshSerializer
