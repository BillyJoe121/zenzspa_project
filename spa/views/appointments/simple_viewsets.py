"""
ViewSets simples para modelos de servicios, paquetes y disponibilidad.
"""
from django.db.models import ProtectedError
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import CustomUser
from users.permissions import IsAdminUser, IsStaff

from ...models import Package, Service, ServiceCategory, StaffAvailability
from ...permissions import IsAdminOrReadOnly
from ...serializers import (
    PackageSerializer,
    ServiceCategorySerializer,
    ServiceSerializer,
    StaffAvailabilitySerializer,
)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet para categorías de servicios."""
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        """
        Sobrescribe el método de eliminación para manejar la protección
        de integridad referencial de forma elegante.
        """
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProtectedError:
            payload = {
                "code": "SRV-001",
                "detail": "Esta categoría no puede eliminarse porque aún tiene servicios asociados. Reasigna o elimina los servicios antes de intentarlo nuevamente.",
            }
            return Response(payload, status=status.HTTP_409_CONFLICT)


class ServiceViewSet(viewsets.ModelViewSet):
    """ViewSet para servicios."""
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        base = Service.objects.all()
        user = getattr(self.request, "user", None)
        if user and getattr(user, "role", None) == CustomUser.Role.ADMIN:
            return base
        return base.filter(is_active=True)


class PackageViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet de solo lectura para paquetes."""
    queryset = Package.objects.filter(is_active=True)
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]


class StaffAvailabilityViewSet(viewsets.ModelViewSet):
    """ViewSet para disponibilidad de staff."""
    serializer_class = StaffAvailabilitySerializer
    permission_classes = [IsAuthenticated, (IsAdminUser | IsStaff)]

    def get_queryset(self):
        user = self.request.user
        base_queryset = StaffAvailability.objects.select_related('staff_member')
        
        # Filtrar solo staff activos (excluir eliminados/inactivos)
        base_queryset = base_queryset.filter(staff_member__is_active=True)
        
        if user.role == CustomUser.Role.ADMIN:
            return base_queryset.all()
        return base_queryset.filter(staff_member=user)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == CustomUser.Role.STAFF:
            serializer.save(staff_member=user)
        elif user.role == CustomUser.Role.ADMIN:
            serializer.save()
