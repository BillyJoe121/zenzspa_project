from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientCreditViewSet, PaymentHistoryView

router = DefaultRouter()
router.register(r'vouchers', ClientCreditViewSet, basename='client-credit')

urlpatterns = [
    path('', include(router.urls)),
    path('payments/my/', PaymentHistoryView.as_view(), name='payment-history'),
]
