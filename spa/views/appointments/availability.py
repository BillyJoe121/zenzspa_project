"""
Vista para verificación de disponibilidad de horarios.
"""
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsVerified

from ...serializers import AvailabilityCheckSerializer


class AvailabilityCheckView(generics.GenericAPIView):
    """Vista para verificar disponibilidad de horarios."""
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = AvailabilityCheckSerializer

    def get(self, request, *args, **kwargs):
        """Obtiene horarios disponibles basado en servicios y fechas."""
        params = request.query_params.copy()
        if 'service_ids' in params:
            params.setlist('service_ids', request.query_params.getlist('service_ids'))
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        available_slots = serializer.get_available_slots()
        return Response(available_slots, status=status.HTTP_200_OK)
