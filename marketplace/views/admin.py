from django.db import transaction
from rest_framework import mixins, viewsets

from users.permissions import (
    IsAdminUser as DomainIsAdminUser,
    IsStaffOrAdmin as DomainIsStaffOrAdmin,
)

from ..models import (
    InventoryMovement,
    Order,
    Product,
    ProductImage,
    ProductVariant,
    ProductVariantImage,
)
from ..serializers import (
    AdminInventoryMovementSerializer,
    AdminOrderSerializer,
    AdminProductImageSerializer,
    AdminProductSerializer,
    AdminProductVariantImageSerializer,
    AdminProductVariantSerializer,
)

class AdminProductViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para productos."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = Product.objects.all().prefetch_related('variants', 'images')
    serializer_class = AdminProductSerializer


class AdminProductVariantViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para variantes de producto."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = ProductVariant.objects.select_related('product')
    serializer_class = AdminProductVariantSerializer


class AdminProductImageViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para imágenes de producto."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = ProductImage.objects.select_related('product')
    serializer_class = AdminProductImageSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']


class AdminProductVariantImageViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para imágenes de variantes de producto."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = ProductVariantImage.objects.select_related('variant__product')
    serializer_class = AdminProductVariantImageSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    def get_queryset(self):
        """Opcionalmente filtra por variante."""
        queryset = super().get_queryset()
        variant_id = self.request.query_params.get('variant', None)
        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)
        return queryset


class AdminInventoryMovementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Permite registrar movimientos de inventario y consultarlos."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = InventoryMovement.objects.select_related(
        'variant__product',
        'reference_order',
        'created_by',
    )
    serializer_class = AdminInventoryMovementSerializer
    http_method_names = ['get', 'post']

    def perform_create(self, serializer):
        with transaction.atomic():
            movement = serializer.save(created_by=self.request.user)
            self._apply_inventory_effect(movement)
            return movement

    def _apply_inventory_effect(self, movement):
        variant = ProductVariant.objects.select_for_update().get(pk=movement.variant_id)
        delta_stock, delta_reserved = AdminInventoryMovementSerializer.compute_deltas(
            movement.movement_type,
            movement.quantity,
        )
        update_fields = []
        if delta_stock:
            variant.stock = variant.stock + delta_stock
            update_fields.append('stock')
        if delta_reserved:
            variant.reserved_stock = variant.reserved_stock + delta_reserved
            update_fields.append('reserved_stock')
        if update_fields:
            variant.save(update_fields=update_fields)


class AdminOrderViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para órdenes."""
    permission_classes = [DomainIsAdminUser]
    serializer_class = AdminOrderSerializer
    queryset = Order.objects.select_related('user').prefetch_related('items__variant__product').order_by('-created_at')

    http_method_names = ['get', 'put', 'patch', 'delete']

    def perform_update(self, serializer):
        order = serializer.save()
        return order
