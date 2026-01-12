"""
Vistas para gestión de sesiones de usuario.
"""
import logging

from rest_framework import generics, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import UserSession
from ..serializers import UserSessionSerializer
from .utils import deactivate_session_for_jti, revoke_all_sessions

logger = logging.getLogger(__name__)


class LogoutView(views.APIView):
    """Cierra sesión individual del usuario."""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({"error": "Se requiere el token refresh."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh)
            token.blacklist()
            jti = str(token['jti'])
            deactivate_session_for_jti(request.user, jti)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TokenError as exc:
            return Response({"error": f"No se pudo cerrar la sesión: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Error desconocido al cerrar sesión."}, status=status.HTTP_400_BAD_REQUEST)


class LogoutAllView(views.APIView):
    """Cierra todas las sesiones del usuario."""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        revoke_all_sessions(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserSessionListView(generics.ListAPIView):
    """Lista las sesiones activas del usuario."""
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True).order_by('-last_activity')


class UserSessionDeleteView(generics.DestroyAPIView):
    """Elimina una sesión específica del usuario."""
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True)

    def perform_destroy(self, instance):
        try:
            token = OutstandingToken.objects.get(jti=instance.refresh_token_jti)
            BlacklistedToken.objects.get_or_create(token=token)
        except OutstandingToken.DoesNotExist:
            pass
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
