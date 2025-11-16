from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AppointmentViewSet,
    AvailabilityCheckView,
    WompiWebhookView,
    StaffAvailabilityViewSet,
    UserPackageViewSet,
    VoucherViewSet,
    InitiatePackagePurchaseView,
    InitiateAppointmentPaymentView,
    InitiateVipSubscriptionView,
    CancelVipSubscriptionView,
    FinancialAdjustmentView,
)

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'staff-availability', StaffAvailabilityViewSet, basename='staff-availability')
router.register(r'my-packages', UserPackageViewSet, basename='my-package')
router.register(r'my-vouchers', VoucherViewSet, basename='my-voucher')


urlpatterns = [
    path('', include(router.urls)),
    path('availability/blocks/', AvailabilityCheckView.as_view(), name='availability-check'),
    path('purchase-package/', InitiatePackagePurchaseView.as_view(), name='purchase-package'),
    path('subscribe-vip/', InitiateVipSubscriptionView.as_view(), name='subscribe-vip'),
    path('vip/cancel-subscription/', CancelVipSubscriptionView.as_view(), name='cancel-vip-subscription'),
    path('payments/webhook/', WompiWebhookView.as_view(), name='payment-webhook'),
    path('appointments/<uuid:pk>/initiate-advance-payment/', InitiateAppointmentPaymentView.as_view(), name='initiate-appointment-payment'),
    path('financial-adjustments/', FinancialAdjustmentView.as_view(), name='financial-adjustments'),
]
