from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.models import CustomUser
from users.permissions import IsAdminUser as DomainIsAdminUser

from ..models import ProductReview
from ..serializers import (
    AdminReviewResponseSerializer,
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    ProductReviewUpdateSerializer,
)

class ProductReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar reseñas de productos.
    - Los usuarios autenticados pueden crear, ver, actualizar y eliminar sus propias reseñas.
    - Los administradores pueden moderar y responder a cualquier reseña.
    """
    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """
        Los usuarios regulares ven solo reseñas aprobadas.
        Los administradores pueden ver todas las reseñas.
        """
        user = self.request.user
        queryset = ProductReview.objects.select_related('user', 'product')

        # Filtrar por producto si se especifica
        product_id = self.request.query_params.get('product', None)
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        # Los admins ven todas, los demás solo las aprobadas
        if not (user.is_authenticated and getattr(user, 'role', None) in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]):
            queryset = queryset.filter(is_approved=True)

        return queryset

    def get_serializer_class(self):
        """Selecciona el serializador según la acción."""
        if self.action == 'create':
            return ProductReviewCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ProductReviewUpdateSerializer
        return ProductReviewSerializer

    def perform_create(self, serializer):
        """Asigna el usuario actual a la reseña."""
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        """Solo permite actualizar reseñas propias."""
        if serializer.instance.user != self.request.user:
            raise PermissionError("No puedes editar reseñas de otros usuarios.")
        serializer.save()

    def perform_destroy(self, instance):
        """Solo permite eliminar reseñas propias o ser admin."""
        user = self.request.user
        is_admin = getattr(user, 'role', None) in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]

        if instance.user != user and not is_admin:
            raise PermissionError("No puedes eliminar reseñas de otros usuarios.")
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[DomainIsAdminUser])
    def respond(self, request, pk=None):
        """
        Permite a los administradores responder a una reseña.
        POST /api/v1/reviews/{id}/respond/
        Body: { "admin_response": "Gracias por tu comentario...", "is_approved": true }
        """
        review = self.get_object()
        serializer = AdminReviewResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review.admin_response = serializer.validated_data['admin_response']
        if 'is_approved' in serializer.validated_data:
            review.is_approved = serializer.validated_data['is_approved']
        review.save()

        return Response(ProductReviewSerializer(review).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_reviews(self, request):
        """
        Lista todas las reseñas del usuario autenticado.
        GET /api/v1/reviews/my_reviews/
        """
        reviews = ProductReview.objects.filter(user=request.user).select_related('product')
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)
