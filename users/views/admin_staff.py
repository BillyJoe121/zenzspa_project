"""
Vistas administrativas para listar personal.
"""
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from ..models import CustomUser
from ..serializers import StaffListSerializer


class StaffListView(generics.ListAPIView):
    """Lista todos los usuarios con rol de staff."""

    serializer_class = StaffListSerializer
    permission_classes = [IsAuthenticated]  # Cambiado para permitir acceso a usuarios autenticados

    def get_queryset(self):
        # Filtrar solo staff activos (excluir eliminados)
        return CustomUser.objects.filter(
            role=CustomUser.Role.STAFF,
            is_active=True
        )
