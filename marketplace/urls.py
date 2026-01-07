from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet,
    CartViewSet,
    OrderViewSet,
    ProductReviewViewSet,
    AdminProductViewSet,
    AdminProductVariantViewSet,
    AdminProductImageViewSet,
    AdminProductVariantImageViewSet,
    AdminInventoryMovementViewSet,
    AdminOrderViewSet,
    ProductCategoryViewSet,
)

router = DefaultRouter()

# Endpoint público para ver el catálogo de productos
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', ProductCategoryViewSet, basename='product-category')

# Endpoints privados para que el usuario gestione su carrito
router.register(r'cart', CartViewSet, basename='cart')

# Endpoints privados de solo lectura para que el usuario vea su historial de órdenes
router.register(r'orders', OrderViewSet, basename='order')

# Endpoints para reseñas de productos
router.register(r'reviews', ProductReviewViewSet, basename='review')

# Endpoints administrativos
router.register(r'admin/products', AdminProductViewSet, basename='admin-product')
router.register(r'admin/variants', AdminProductVariantViewSet, basename='admin-product-variant')
router.register(r'admin/product-images', AdminProductImageViewSet, basename='admin-product-image')
router.register(r'admin/variant-images', AdminProductVariantImageViewSet, basename='admin-variant-image')
router.register(r'admin/inventory-movements', AdminInventoryMovementViewSet, basename='admin-inventory-movement')
router.register(r'admin/orders', AdminOrderViewSet, basename='admin-order')


urlpatterns = [
    path('', include(router.urls)),
]

