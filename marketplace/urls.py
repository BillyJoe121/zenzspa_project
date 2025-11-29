from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CartViewSet, OrderViewSet, ProductReviewViewSet

router = DefaultRouter()

# Endpoint público para ver el catálogo de productos
router.register(r'products', ProductViewSet, basename='product')

# Endpoints privados para que el usuario gestione su carrito
router.register(r'cart', CartViewSet, basename='cart')

# Endpoints privados de solo lectura para que el usuario vea su historial de órdenes
router.register(r'orders', OrderViewSet, basename='order')

# Endpoints para reseñas de productos
router.register(r'reviews', ProductReviewViewSet, basename='review')


urlpatterns = [
    path('', include(router.urls)),
]