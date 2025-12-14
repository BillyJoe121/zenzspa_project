from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, F

from .models import Article, Category, Tag, ArticleImage
from .serializers import (
    ArticleListSerializer,
    ArticleDetailSerializer,
    ArticleCreateUpdateSerializer,
    CategorySerializer,
    TagSerializer,
    ArticleImageSerializer
)
from .permissions import IsAdminOrReadOnly


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de categorías del blog
    - GET /api/v1/blog/categories/ - Lista todas las categorías
    - POST /api/v1/blog/categories/ - Crear categoría (solo admin)
    - GET /api/v1/blog/categories/{id}/ - Detalle de categoría
    - PUT/PATCH /api/v1/blog/categories/{id}/ - Actualizar (solo admin)
    - DELETE /api/v1/blog/categories/{id}/ - Eliminar (solo admin)
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class TagViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de etiquetas del blog
    - GET /api/v1/blog/tags/ - Lista todas las etiquetas
    - POST /api/v1/blog/tags/ - Crear etiqueta (solo admin)
    - GET /api/v1/blog/tags/{id}/ - Detalle de etiqueta
    - PUT/PATCH /api/v1/blog/tags/{id}/ - Actualizar (solo admin)
    - DELETE /api/v1/blog/tags/{id}/ - Eliminar (solo admin)
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class ArticleViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de artículos del blog

    Endpoints públicos (sin autenticación):
    - GET /api/v1/blog/articles/ - Lista artículos publicados
    - GET /api/v1/blog/articles/{slug}/ - Detalle de artículo publicado
    - GET /api/v1/blog/articles/featured/ - Artículos destacados

    Endpoints admin (requiere autenticación y permisos):
    - POST /api/v1/blog/articles/ - Crear artículo
    - PUT/PATCH /api/v1/blog/articles/{slug}/ - Actualizar artículo
    - DELETE /api/v1/blog/articles/{slug}/ - Eliminar artículo
    - POST /api/v1/blog/articles/{slug}/publish/ - Publicar artículo
    - POST /api/v1/blog/articles/{slug}/unpublish/ - Despublicar artículo

    Filtros disponibles:
    - ?category=slug - Filtrar por categoría
    - ?tag=slug - Filtrar por etiqueta
    - ?status=published|draft|archived - Filtrar por estado (solo admin)
    - ?search=texto - Buscar en título, subtítulo y contenido
    - ?ordering=-published_at - Ordenar resultados
    """
    queryset = Article.objects.select_related('category', 'author').prefetch_related('tags', 'images')
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'subtitle', 'content', 'excerpt']
    ordering_fields = ['published_at', 'created_at', 'updated_at', 'views_count', 'title']
    ordering = ['-published_at', '-created_at']
    filterset_fields = {
        'status': ['exact'],
        'category__slug': ['exact'],
        'tags__slug': ['exact'],
        'is_featured': ['exact'],
    }

    def get_queryset(self):
        """
        Los usuarios no autenticados solo ven artículos publicados.
        Los administradores ven todos los artículos.
        """
        queryset = super().get_queryset()

        # Si es admin, mostrar todos
        if self.request.user and self.request.user.is_staff:
            return queryset

        # Para usuarios normales, solo artículos publicados
        return queryset.filter(
            status='published',
            published_at__lte=timezone.now()
        )

    def get_serializer_class(self):
        """Usar diferentes serializers según la acción"""
        if self.action == 'list':
            return ArticleListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ArticleCreateUpdateSerializer
        return ArticleDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        """Incrementar contador de vistas al ver detalle"""
        instance = self.get_object()

        # Incrementar vistas (solo para artículos publicados)
        if instance.status == 'published':
            Article.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
            instance.refresh_from_db()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticatedOrReadOnly])
    def featured(self, request):
        """
        GET /api/v1/blog/articles/featured/
        Retorna artículos destacados (publicados)
        """
        featured_articles = self.get_queryset().filter(
            is_featured=True,
            status='published'
        ).order_by('-featured_order', '-published_at')[:6]

        serializer = ArticleListSerializer(featured_articles, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticatedOrReadOnly])
    def recent(self, request):
        """
        GET /api/v1/blog/articles/recent/
        Retorna artículos recientes (últimos 10 publicados)
        """
        recent_articles = self.get_queryset().filter(
            status='published'
        ).order_by('-published_at')[:10]

        serializer = ArticleListSerializer(recent_articles, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticatedOrReadOnly])
    def popular(self, request):
        """
        GET /api/v1/blog/articles/popular/
        Retorna artículos más vistos (publicados)
        """
        popular_articles = self.get_queryset().filter(
            status='published'
        ).order_by('-views_count', '-published_at')[:10]

        serializer = ArticleListSerializer(popular_articles, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def publish(self, request, slug=None):
        """
        POST /api/v1/blog/articles/{slug}/publish/
        Publica un artículo (solo admin)
        """
        article = self.get_object()

        if article.status == 'published':
            return Response(
                {'detail': 'El artículo ya está publicado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        article.status = 'published'
        if not article.published_at:
            article.published_at = timezone.now()
        article.save()

        serializer = self.get_serializer(article)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def unpublish(self, request, slug=None):
        """
        POST /api/v1/blog/articles/{slug}/unpublish/
        Despublica un artículo (cambia a borrador)
        """
        article = self.get_object()

        if article.status != 'published':
            return Response(
                {'detail': 'El artículo no está publicado.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        article.status = 'draft'
        article.save()

        serializer = self.get_serializer(article)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAdminUser])
    def images(self, request, slug=None):
        """
        GET /api/v1/blog/articles/{slug}/images/ - Listar imágenes del artículo
        POST /api/v1/blog/articles/{slug}/images/ - Agregar imagen al artículo
        """
        article = self.get_object()

        if request.method == 'GET':
            images = article.images.all()
            serializer = ArticleImageSerializer(images, many=True, context={'request': request})
            return Response(serializer.data)

        elif request.method == 'POST':
            serializer = ArticleImageSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save(article=article)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ArticleImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de imágenes de artículos (solo admin)
    """
    queryset = ArticleImage.objects.all()
    serializer_class = ArticleImageSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'created_at']
    ordering = ['order', 'created_at']

    def get_queryset(self):
        """Filtrar por artículo si se proporciona"""
        queryset = super().get_queryset()
        article_id = self.request.query_params.get('article_id')

        if article_id:
            queryset = queryset.filter(article_id=article_id)

        return queryset
