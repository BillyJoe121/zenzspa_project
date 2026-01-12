from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AppointmentViewSet,
    AvailabilityCheckView,
    StaffAvailabilityViewSet,
    UserPackageViewSet,
    VoucherViewSet,
    AdminPackageViewSet,
    CancelVipSubscriptionView,
    FinancialAdjustmentView,
    AdminVoucherViewSet,
)
from finances.views import ClientCreditBalanceView
from .views.history import ClientAppointmentHistoryView
from .viewsets import (
    ServiceViewSet,
    ServiceCategoryViewSet,
    AvailabilityExclusionViewSet,
)
from .views.appointments.simple_viewsets import ServiceMediaViewSet

router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'staff-availability', StaffAvailabilityViewSet, basename='staff-availability')
router.register(r'my-packages', UserPackageViewSet, basename='my-package')
router.register(r'my-vouchers', VoucherViewSet, basename='my-voucher')
router.register(r'admin/vouchers', AdminVoucherViewSet, basename='admin-voucher')
router.register(r'admin/packages', AdminPackageViewSet, basename='admin-package')

# Nuevos endpoints de administración
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'service-media', ServiceMediaViewSet, basename='service-media')
router.register(r'availability-exclusions', AvailabilityExclusionViewSet, basename='availability-exclusion')


urlpatterns = [
    path('', include(router.urls)),
    path('availability/blocks/', AvailabilityCheckView.as_view(), name='availability-check'),
    path('vip/cancel-subscription/', CancelVipSubscriptionView.as_view(), name='cancel-vip-subscription'),
    path('financial-adjustments/', FinancialAdjustmentView.as_view(), name='financial-adjustments'),
    path('history/', ClientAppointmentHistoryView.as_view(), name='client-appointment-history'),
    
    # Alias para compatibilidad con frontend (credits/balance/ -> finances/views)
    path('credits/balance/', ClientCreditBalanceView.as_view(), name='client-credit-balance-alias'),
]
