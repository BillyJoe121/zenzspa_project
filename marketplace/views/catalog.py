from django.utils import timezone
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permissions import IsAdminUser as DomainIsAdminUser

from ..models import Product, ProductCategory
from ..serializers import (
    ProductCategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductVariantSerializer,
)

class ProductCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de categorías de productos del marketplace.

    - LIST/RETRIEVE: Cualquier usuario autenticado
    - CREATE/UPDATE/DELETE: Solo ADMIN
    """
    queryset = ProductCategory.objects.all().order_by('name')
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    
    def get_permissions(self):
        """Solo ADMIN puede crear, actualizar o eliminar categorías."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [DomainIsAdminUser()]
        return super().get_permissions()
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete de la categoría.
        Verifica que no tenga productos activos asociados.
        """
        instance = self.get_object()
        
        active_products = instance.products.filter(is_active=True).count()
        if active_products > 0:
            return Response(
                {
                    'error': f'No se puede eliminar la categoría porque tiene {active_products} producto(s) activo(s) asociado(s).'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete
        instance.deleted_at = timezone.now()
        instance.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)



class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para ver el catálogo de productos.
    Permite listar todos los productos activos y ver el detalle de uno solo.

    Búsqueda disponible:
    - ?search=término : Busca en nombre y descripción del producto
    - ?category=uuid : Filtra por categoría
    - ?min_price=100 : Precio mínimo
    - ?max_price=500 : Precio máximo
    - ?in_stock=true : Solo productos con stock disponible
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = (
        Product.objects.filter(is_active=True)
        .prefetch_related('images', 'variants')
    )

    def get_serializer_class(self):
        """
        Devuelve un serializador diferente para la vista de lista y la de detalle,
        como lo diseñamos previamente.
        """
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    def get_queryset(self):
        """
        Filtra productos según parámetros de búsqueda.
        """
        queryset = super().get_queryset()

        # Búsqueda por texto en nombre y descripción
        search = self.request.query_params.get('search', None)
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # Filtro por categoría
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category_id=category)

        # Filtro por rango de precio
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)

        if min_price or max_price:
            # Filtrar productos que tengan al menos una variante en el rango
            from django.db.models import Min
            queryset = queryset.annotate(lowest_price=Min('variants__price'))

            if min_price:
                queryset = queryset.filter(lowest_price__gte=min_price)
            if max_price:
                queryset = queryset.filter(lowest_price__lte=max_price)

        # Filtro por disponibilidad de stock
        in_stock = self.request.query_params.get('in_stock', None)
        if in_stock and in_stock.lower() in ['true', '1', 'yes']:
            # Solo productos con al menos una variante con stock disponible
            from django.db.models import Sum, F
            queryset = queryset.annotate(
                total_available=Sum(F('variants__stock') - F('variants__reserved_stock'))
            ).filter(total_available__gt=0)

        return queryset

    @action(detail=True, methods=['get'])
    def variants(self, request, pk=None):
        """
        Lista las variantes del producto solicitado.
        GET /api/v1/products/{id}/variants/
        """
        product = self.get_object()
        serializer = ProductVariantSerializer(
            product.variants.all(),
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """
        Lista las reseñas aprobadas de un producto.
        GET /api/v1/products/{id}/reviews/
        """
        product = self.get_object()
        reviews = product.reviews.filter(is_approved=True).select_related('user')
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)
