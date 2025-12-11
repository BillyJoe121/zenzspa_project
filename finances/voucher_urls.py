from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientCreditViewSet

router = DefaultRouter()
router.register(r'vouchers', ClientCreditViewSet, basename='client-credit')

urlpatterns = [
    path('', include(router.urls)),
]
