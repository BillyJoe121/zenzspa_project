"""
ViewSets para gestión de configuraciones del sistema.
"""
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsAdminUser, IsAdminUser as IsAdminUserPermission
from core.models import GlobalSettings
from .serializers import GlobalSettingsUpdateSerializer


class GlobalSettingsViewSet(viewsets.ViewSet):
    """
    ViewSet para gestión de configuraciones globales del sistema.
    
    Solo permite GET y UPDATE (no DELETE ni CREATE ya que es un singleton).
    Requiere permisos de ADMIN para modificar.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        GET /api/v1/core/settings/
        
        Retorna la configuración global del sistema.
        Los campos sensibles solo son visibles para ADMIN.
        """
        from core.serializers import GlobalSettingsSerializer
        
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(serializer.data)
    
    def update(self, request, pk=None):
        """
        PUT /api/v1/core/settings/{id}/
        
        Actualiza la configuración global del sistema.
        Solo ADMIN puede modificar.
        """
        if not request.user.role == 'ADMIN':
            return Response(
                {'detail': 'Solo administradores pueden modificar la configuración global.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsUpdateSerializer(
            settings_obj,
            data=request.data,
            partial=False,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la configuración actualizada
        from core.serializers import GlobalSettingsSerializer
        response_serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(response_serializer.data)
    
    def partial_update(self, request, pk=None):
        """
        PATCH /api/v1/core/settings/{id}/
        
        Actualiza parcialmente la configuración global del sistema.
        Solo ADMIN puede modificar.
        """
        if not request.user.role == 'ADMIN':
            return Response(
                {'detail': 'Solo administradores pueden modificar la configuración global.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        settings_obj = GlobalSettings.load()
        serializer = GlobalSettingsUpdateSerializer(
            settings_obj,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la configuración actualizada
        from core.serializers import GlobalSettingsSerializer
        response_serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response(response_serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def reset_to_defaults(self, request):
        """
        POST /api/v1/core/settings/reset_to_defaults/
        
        Reinicia la configuración a valores por defecto.
        Solo ADMIN puede ejecutar esta acción.
        """
        settings_obj = GlobalSettings.load()
        
        # Reiniciar a defaults
        settings_obj.low_supervision_capacity = 1
        settings_obj.advance_payment_percentage = 40
        settings_obj.appointment_buffer_time = 10
        settings_obj.vip_monthly_price = 0
        settings_obj.advance_expiration_minutes = 20
        settings_obj.credit_expiration_days = 365
        settings_obj.return_window_days = 30
        settings_obj.no_show_credit_policy = GlobalSettings.NoShowCreditPolicy.NONE
        settings_obj.loyalty_months_required = 3
        settings_obj.waitlist_enabled = False
        settings_obj.waitlist_ttl_minutes = 60
        settings_obj.timezone_display = "America/Bogota"
        
        settings_obj.save()
        
        from core.serializers import GlobalSettingsSerializer
        serializer = GlobalSettingsSerializer(settings_obj, context={'request': request})
        return Response({
            'message': 'Configuración reiniciada a valores por defecto',
            'settings': serializer.data
        })


class AboutPageViewSet(viewsets.ViewSet):
    """
    ViewSet para gestión de la página "Quiénes Somos".
    
    - GET: Cualquier usuario (público)
    - UPDATE: Solo ADMIN
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        GET /api/v1/core/about/
        
        Retorna el contenido de la página Quiénes Somos.
        Público (no requiere autenticación para lectura).
        """
        from core.models import AboutPage
        from core.serializers_about import AboutPageSerializer
        
        about_page = AboutPage.load()
        serializer = AboutPageSerializer(about_page, context={'request': request})
        return Response(serializer.data)
    
    def update(self, request, pk=None):
        """
        PUT /api/v1/core/about/{id}/
        
        Actualiza la página Quiénes Somos.
        Solo ADMIN puede modificar.
        """
        if not request.user.role == 'ADMIN':
            return Response(
                {'detail': 'Solo administradores pueden modificar la página Quiénes Somos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from core.models import AboutPage
        from core.serializers_about import AboutPageUpdateSerializer, AboutPageSerializer
        
        about_page = AboutPage.load()
        serializer = AboutPageUpdateSerializer(
            about_page,
            data=request.data,
            partial=False,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la página actualizada
        response_serializer = AboutPageSerializer(about_page, context={'request': request})
        return Response(response_serializer.data)
    
    def partial_update(self, request, pk=None):
        """
        PATCH /api/v1/core/about/{id}/
        
        Actualiza parcialmente la página Quiénes Somos.
        Solo ADMIN puede modificar.
        """
        if not request.user.role == 'ADMIN':
            return Response(
                {'detail': 'Solo administradores pueden modificar la página Quiénes Somos.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from core.models import AboutPage
        from core.serializers_about import AboutPageUpdateSerializer, AboutPageSerializer
        
        about_page = AboutPage.load()
        serializer = AboutPageUpdateSerializer(
            about_page,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Retornar la página actualizada
        response_serializer = AboutPageSerializer(about_page, context={'request': request})
        return Response(response_serializer.data)


class TeamMemberViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de miembros del equipo.
    
    - LIST/RETRIEVE: Público (solo miembros activos)
    - CREATE/UPDATE/DELETE: Solo ADMIN
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'name', 'created_at']
    ordering = ['order', 'name']
    
    def get_queryset(self):
        """
        Usuarios no autenticados solo ven miembros activos.
        Admins ven todos.
        """
        from core.models import TeamMember
        
        queryset = TeamMember.objects.all()
        
        if not (self.request.user and self.request.user.role == 'ADMIN'):
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def get_serializer_class(self):
        from core.serializers_about import TeamMemberSerializer
        return TeamMemberSerializer
    
    def get_permissions(self):
        """
        Solo ADMIN puede crear, actualizar o eliminar miembros.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.AllowAny()]


class GalleryImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de imágenes de la galería.
    
    - LIST/RETRIEVE: Público (solo imágenes activas)
    - CREATE/UPDATE/DELETE: Solo ADMIN
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'created_at']
    ordering = ['order', 'created_at']
    
    def get_queryset(self):
        """
        Usuarios no autenticados solo ven imágenes activas.
        Admins ven todas.
        """
        from core.models import GalleryImage
        
        queryset = GalleryImage.objects.all()
        
        if not (self.request.user and self.request.user.role == 'ADMIN'):
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def get_serializer_class(self):
        from core.serializers_about import GalleryImageSerializer
        return GalleryImageSerializer
    
    def get_permissions(self):
        """
        Solo ADMIN puede crear, actualizar o eliminar imágenes.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [permissions.AllowAny()]
