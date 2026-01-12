from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ServiceCategoryViewSet, ServiceViewSet, PackageViewSet

router = DefaultRouter()
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'packages', PackageViewSet, basename='package')

urlpatterns = [
    path('', include(router.urls)),
]
