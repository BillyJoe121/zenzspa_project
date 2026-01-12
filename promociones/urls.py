from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PromocionViewSet

app_name = 'promociones'

router = DefaultRouter()
router.register(r'', PromocionViewSet, basename='promocion')

urlpatterns = [
    path('', include(router.urls)),
]
