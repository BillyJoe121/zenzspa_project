"""
ViewSets simples para modelos de servicios, paquetes y disponibilidad.
"""
from django.db.models import ProtectedError
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as django_filters

from users.models import CustomUser
from users.permissions import IsAdminUser, IsStaff

from ...models import Package, Service, ServiceCategory, ServiceMedia, StaffAvailability
from ...permissions import IsAdminOrReadOnly
from ...serializers import (
    PackageSerializer,
    ServiceCategorySerializer,
    ServiceMediaSerializer,
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


class ServiceFilter(django_filters.FilterSet):
    """Filtro explícito para Servicios en el catálogo público."""
    category = django_filters.UUIDFilter(field_name='category__id')
    is_active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = Service
        fields = ['category', 'is_active']


class ServiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet para servicios del catálogo público.

    Filtros disponibles:
    - category: UUID de la categoría (ej: ?category=uuid)
    - is_active: true/false
    - search: búsqueda por nombre o descripción
    """
    queryset = Service.objects.select_related('category').filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ServiceFilter
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'duration', 'created_at']

    def get_queryset(self):
        """Filtrar servicios según rol del usuario."""
        base = Service.objects.select_related('category').prefetch_related('media').all()
        user = getattr(self.request, "user", None)
        if user and getattr(user, "role", None) == CustomUser.Role.ADMIN:
            return base
        return base.filter(is_active=True)


class ServiceMediaFilter(django_filters.FilterSet):
    """Filtro para medios de servicios."""
    service = django_filters.UUIDFilter(field_name='service__id')
    media_type = django_filters.ChoiceFilter(choices=ServiceMedia.MediaType.choices)

    class Meta:
        model = ServiceMedia
        fields = ['service', 'media_type']


class ServiceMediaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de medios de servicios (imágenes/videos).

    Solo administradores pueden crear, editar y eliminar.
    Cualquier usuario autenticado puede ver los medios.

    Filtros disponibles:
    - service: UUID del servicio (ej: ?service=uuid)
    - media_type: IMAGE o VIDEO
    """
    queryset = ServiceMedia.objects.select_related('service').all()
    serializer_class = ServiceMediaSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ServiceMediaFilter
    ordering_fields = ['display_order', 'created_at']
    ordering = ['display_order', 'created_at']


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
