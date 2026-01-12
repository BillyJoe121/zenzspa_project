"""
Vistas relacionadas con el usuario autenticado.
"""
import logging
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..serializers import SimpleUserSerializer

logger = logging.getLogger(__name__)


class CurrentUserView(generics.RetrieveAPIView):
    """Obtiene información del usuario actual autenticado."""

    permission_classes = [IsAuthenticated]
    serializer_class = SimpleUserSerializer

    def get_object(self):
        return self.request.user


class UserDeleteView(views.APIView):
    """
    Permite al usuario eliminar su propia cuenta (GDPR).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        user = request.user
        # Soft delete
        user.is_active = False
        user.is_deleted = True
        user.phone_number = f"{user.phone_number}_deleted_{timezone.now().timestamp()}"
        user.email = f"deleted_{timezone.now().timestamp()}_{user.email}"
        user.save()

        # Revoke sessions
        from .utils import revoke_all_sessions
        revoke_all_sessions(user)

        logger.info(f"User {user.id} deleted their account.")

        return Response(status=status.HTTP_204_NO_CONTENT)
