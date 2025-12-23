"""
ViewSets para gestión de servicios, categorías y disponibilidad.
"""
from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
from django_filters import rest_framework as django_filters

from users.permissions import IsAdminUser
from spa.models import Service, ServiceCategory, AvailabilityExclusion, Appointment, StaffAvailability
from spa.serializers import ServiceSerializer, ServiceCategorySerializer


class ServiceFilter(django_filters.FilterSet):
    """Filtro explícito para Servicios."""
    category = django_filters.UUIDFilter(field_name='category__id')
    is_active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = Service
        fields = ['category', 'is_active']


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de categorías de servicios.
    
    - LIST/RETRIEVE: Cualquier usuario autenticado
    - CREATE/UPDATE/DELETE: Solo ADMIN
    """
    queryset = ServiceCategory.objects.all().order_by('name')
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    
    def get_permissions(self):
        """
        Solo ADMIN puede crear, actualizar o eliminar categorías.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return super().get_permissions()
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete de la categoría.
        Verifica que no tenga servicios activos asociados.
        """
        instance = self.get_object()
        
        # Verificar si tiene servicios activos
        active_services = instance.services.filter(is_active=True).count()
        if active_services > 0:
            return Response(
                {
                    'error': f'No se puede eliminar la categoría porque tiene {active_services} servicio(s) activo(s) asociado(s).'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete
        instance.deleted_at = timezone.now()
        instance.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def toggle_low_supervision(self, request, pk=None):
        """
        POST /api/v1/spa/service-categories/{id}/toggle_low_supervision/
        
        Cambia el estado de is_low_supervision de la categoría.
        """
        category = self.get_object()
        category.is_low_supervision = not category.is_low_supervision
        category.save()
        
        serializer = self.get_serializer(category)
        return Response({
            'message': f'Categoría marcada como {"baja supervisión" if category.is_low_supervision else "supervisión normal"}',
            'category': serializer.data
        })


class ServiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de servicios.
    
    - LIST/RETRIEVE: Cualquier usuario autenticado
    - CREATE/UPDATE/DELETE: Solo ADMIN
    
    Filtros disponibles:
    - category: UUID de la categoría
    - is_active: true/false
    - search: búsqueda por nombre o descripción
    """
    queryset = Service.objects.select_related('category').all().order_by('name')
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ServiceFilter
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'duration', 'created_at']
    
    def get_queryset(self):
        """
        Filtrar servicios eliminados (soft delete).
        """
        queryset = super().get_queryset()
        
        # Por defecto, no mostrar servicios eliminados
        if not self.request.query_params.get('include_deleted'):
            queryset = queryset.filter(deleted_at__isnull=True)
        
        return queryset
    
    def get_permissions(self):
        """
        Solo ADMIN puede crear, actualizar o eliminar servicios.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return super().get_permissions()
    
    def perform_create(self, serializer):
        """
        Crear servicio con validaciones adicionales.
        """
        serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete del servicio.
        Verifica que no tenga citas activas asociadas.
        """
        from django.utils import timezone
        instance = self.get_object()
        
        # Verificar si tiene citas activas futuras
        future_appointments = Appointment.objects.filter(
            services=instance,
            start_time__gte=timezone.now(),
            status__in=['PENDING_PAYMENT', 'CONFIRMED', 'RESCHEDULED']
        ).count()
        
        if future_appointments > 0:
            return Response(
                {
                    'error': f'No se puede eliminar el servicio porque tiene {future_appointments} cita(s) activa(s) asociada(s).'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def toggle_active(self, request, pk=None):
        """
        POST /api/v1/spa/services/{id}/toggle_active/
        
        Activa/desactiva un servicio.
        """
        service = self.get_object()
        service.is_active = not service.is_active
        service.save()
        
        serializer = self.get_serializer(service)
        return Response({
            'message': f'Servicio {"activado" if service.is_active else "desactivado"}',
            'service': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        GET /api/v1/spa/services/active/
        
        Lista solo servicios activos (útil para el frontend de clientes).
        """
        queryset = self.get_queryset().filter(is_active=True)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AvailabilityExclusionSerializer(serializers.ModelSerializer):
    """
    Serializer para exclusiones de disponibilidad.
    """
    staff_member_name = serializers.CharField(
        source='staff_member.get_full_name',
        read_only=True
    )
    day_of_week_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AvailabilityExclusion
        fields = [
            'id',
            'staff_member',
            'staff_member_name',
            'date',
            'day_of_week',
            'day_of_week_display',
            'start_time',
            'end_time',
            'reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_day_of_week_display(self, obj):
        """
        Retorna el nombre del día de la semana si aplica.
        """
        if obj.day_of_week:
            return StaffAvailability.DayOfWeek(obj.day_of_week).label
        return None
    
    def validate(self, data):
        """
        Validaciones personalizadas.
        """
        # Debe tener date O day_of_week (no ambos vacíos)
        if not data.get('date') and not data.get('day_of_week'):
            raise serializers.ValidationError(
                'Debe especificar una fecha específica o un día de la semana.'
            )
        
        # start_time debe ser menor que end_time
        if data.get('start_time') and data.get('end_time'):
            if data['start_time'] >= data['end_time']:
                raise serializers.ValidationError({
                    'start_time': 'La hora de inicio debe ser menor que la hora de fin.'
                })
        
        return data


class AvailabilityExclusionViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de exclusiones de disponibilidad.
    
    Permite bloquear horarios específicos o recurrentes para terapeutas.
    Solo ADMIN puede gestionar exclusiones.
    """
    # Filtrar solo exclusiones de staff activos
    queryset = AvailabilityExclusion.objects.select_related('staff_member').filter(
        staff_member__is_active=True
    ).order_by('-created_at')
    serializer_class = AvailabilityExclusionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['staff_member', 'date', 'day_of_week']
    ordering_fields = ['date', 'start_time', 'created_at']
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """
        GET /api/v1/spa/availability-exclusions/upcoming/
        
        Lista exclusiones futuras (fecha >= hoy).
        """
        from django.utils import timezone
        today = timezone.localdate()
        
        queryset = self.get_queryset().filter(
            models.Q(date__gte=today) | models.Q(date__isnull=True)
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        POST /api/v1/spa/availability-exclusions/bulk_create/
        
        Crea múltiples exclusiones a la vez.
        Útil para bloquear vacaciones o días festivos.
        
        Body: {
            "exclusions": [
                {
                    "staff_member": "uuid",
                    "date": "2025-12-25",
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "reason": "Navidad"
                },
                ...
            ]
        }
        """
        exclusions_data = request.data.get('exclusions', [])
        
        if not exclusions_data:
            return Response(
                {'error': 'Debe proporcionar al menos una exclusión.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_exclusions = []
        errors = []
        
        for idx, exclusion_data in enumerate(exclusions_data):
            serializer = self.get_serializer(data=exclusion_data)
            if serializer.is_valid():
                serializer.save()
                created_exclusions.append(serializer.data)
            else:
                errors.append({
                    'index': idx,
                    'data': exclusion_data,
                    'errors': serializer.errors
                })
        
        return Response({
            'created': len(created_exclusions),
            'failed': len(errors),
            'exclusions': created_exclusions,
            'errors': errors
        }, status=status.HTTP_201_CREATED if created_exclusions else status.HTTP_400_BAD_REQUEST)
