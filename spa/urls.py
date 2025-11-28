from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AppointmentViewSet,
    AvailabilityCheckView,
    StaffAvailabilityViewSet,
    UserPackageViewSet,
    VoucherViewSet,
    CancelVipSubscriptionView,
    FinancialAdjustmentView,
)
from .views.history import ClientAppointmentHistoryView

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'staff-availability', StaffAvailabilityViewSet, basename='staff-availability')
router.register(r'my-packages', UserPackageViewSet, basename='my-package')
router.register(r'my-vouchers', VoucherViewSet, basename='my-voucher')


urlpatterns = [
    path('', include(router.urls)),
    path('availability/blocks/', AvailabilityCheckView.as_view(), name='availability-check'),
    path('vip/cancel-subscription/', CancelVipSubscriptionView.as_view(), name='cancel-vip-subscription'),
    path('financial-adjustments/', FinancialAdjustmentView.as_view(), name='financial-adjustments'),
    path('history/', ClientAppointmentHistoryView.as_view(), name='client-appointment-history'),
]
