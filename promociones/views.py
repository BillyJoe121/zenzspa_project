from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from .models import Promocion
from .serializers import PromocionSerializer, PromocionListSerializer


class PromocionViewSet(viewsets.ModelViewSet):
    """
    ViewSet completo para promociones con CRUD.

    Endpoints públicos (sin autenticación):
    - GET /api/promociones/ - Lista todas las promociones activas
    - GET /api/promociones/{id}/ - Detalle de una promoción
    - GET /api/promociones/activas/ - Promociones activas para una página específica
    - POST /api/promociones/{id}/registrar_vista/ - Incrementa contador de vista
    - POST /api/promociones/{id}/registrar_click/ - Incrementa contador de click

    Endpoints solo para admins (requiere autenticación y permisos):
    - POST /api/promociones/ - Crear nueva promoción
    - PUT /api/promociones/{id}/ - Actualizar promoción completa
    - PATCH /api/promociones/{id}/ - Actualizar promoción parcial
    - DELETE /api/promociones/{id}/ - Eliminar promoción
    """
    queryset = Promocion.objects.all()
    serializer_class = PromocionSerializer
    versioning_class = None  # Deshabilitar versionado para este ViewSet

    def get_permissions(self):
        """
        Permisos personalizados por acción:
        - Lectura y tracking: Públicos (AllowAny)
        - CRUD (crear/editar/eliminar): Solo admins (IsAdminUser)
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [AllowAny()]

    def get_queryset(self):
        """
        Retorna el queryset base.
        - Admins: Todas las promociones (para poder editar/borrar inactivas).
        - Público: Solo promociones activas.
        """
        if self.request.user and self.request.user.is_staff:
            return Promocion.objects.all().order_by('-prioridad', '-creada_en')
        
        return Promocion.objects.filter(
            activa=True
        ).order_by('-prioridad', '-creada_en')

    def get_serializer_class(self):
        """Usa el serializer completo para devolver todos los campos (activa, paginas, etc.)"""
        return PromocionSerializer



    @action(detail=False, methods=['get'], url_path='activas')
    def activas(self, request):
        """
        Retorna promociones activas para una página específica.

        Query params:
        - pagina (opcional): 'dashboard', 'home', 'services', 'shop', 'book'
          Si no se proporciona, retorna todas las promociones vigentes.

        Ejemplo: GET /api/promociones/activas/?pagina=dashboard
        """
        pagina = request.query_params.get('pagina', None)

        # Si se proporciona página, validar que sea válida
        if pagina:
            paginas_validas = dict(Promocion.PAGINA_CHOICES).keys()
            if pagina not in paginas_validas:
                return Response(
                    {
                        'error': f'Página inválida. Opciones: {", ".join(paginas_validas)}'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Filtrar promociones que incluyan esta página
            promociones = Promocion.objects.filter(
                paginas__contains=[pagina]
            ).order_by('-prioridad', '-creada_en')
        else:
            # Si no se proporciona página, retornar todas las promociones activas
            promociones = Promocion.objects.all().order_by('-prioridad', '-creada_en')

        # Filtrar manualmente por vigencia (para considerar fechas)
        promociones_vigentes = [p for p in promociones if p.esta_vigente()]

        serializer = self.get_serializer(promociones_vigentes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='registrar-vista')
    def registrar_vista(self, request, pk=None):
        """
        Incrementa el contador de veces mostrada de una promoción.

        Ejemplo: POST /api/promociones/1/registrar-vista/
        """
        promocion = self.get_object()
        promocion.incrementar_contador_mostrada()
        return Response({'success': True, 'veces_mostrada': promocion.veces_mostrada})

    @action(detail=True, methods=['post'], url_path='registrar-click')
    def registrar_click(self, request, pk=None):
        """
        Incrementa el contador de clics de una promoción.

        Ejemplo: POST /api/promociones/1/registrar-click/
        """
        promocion = self.get_object()
        promocion.incrementar_contador_click()
        return Response({'success': True, 'veces_clickeada': promocion.veces_clickeada})
