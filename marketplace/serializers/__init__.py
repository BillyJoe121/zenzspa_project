"""
Fachada para serializers del marketplace.

Reexporta los serializadores divididos en módulos más pequeños manteniendo
compatibilidad con ``from marketplace.serializers import ...``.
"""

from .admin import (
    AdminInventoryMovementSerializer,
    AdminProductImageSerializer,
    AdminProductSerializer,
    AdminProductVariantImageSerializer,
    AdminProductVariantSerializer,
)
from .cart import CartItemCreateUpdateSerializer, CartItemSerializer, CartSerializer
from .catalog import (
    ProductCategorySerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantImageSerializer,
    ProductVariantSerializer,
)
from .orders import (
    AdminOrderSerializer,
    CheckoutSerializer,
    OrderItemSerializer,
    OrderSerializer,
    ReturnDecisionSerializer,
    ReturnItemInputSerializer,
    ReturnRequestSerializer,
)
from .reviews import (
    AdminReviewResponseSerializer,
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    ProductReviewUpdateSerializer,
)
from .shared import _show_sensitive_data, ImageUrlMixin

__all__ = [
    "ProductCategorySerializer",
    "ProductImageSerializer",
    "ProductVariantImageSerializer",
    "ProductVariantSerializer",
    "ProductListSerializer",
    "ProductDetailSerializer",
    "CartItemSerializer",
    "CartSerializer",
    "CartItemCreateUpdateSerializer",
    "OrderItemSerializer",
    "OrderSerializer",
    "AdminOrderSerializer",
    "CheckoutSerializer",
    "ReturnItemInputSerializer",
    "ReturnRequestSerializer",
    "ReturnDecisionSerializer",
    "ProductReviewSerializer",
    "ProductReviewCreateSerializer",
    "ProductReviewUpdateSerializer",
    "AdminReviewResponseSerializer",
    "AdminProductSerializer",
    "AdminProductVariantSerializer",
    "AdminProductImageSerializer",
    "AdminProductVariantImageSerializer",
    "AdminInventoryMovementSerializer",
    "_show_sensitive_data",
    "ImageUrlMixin",
]
