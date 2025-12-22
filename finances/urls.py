"""
URLs para el módulo finances.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientCreditAdminViewSet,
    CommissionLedgerListView,
    CommissionLedgerDetailView,
    DeveloperCommissionStatusView,
    ManualDeveloperPayoutView,
    PSEFinancialInstitutionsView,
    InitiateAppointmentPaymentView,
    WompiWebhookView,
    InitiateVipSubscriptionView,
    InitiatePackagePurchaseView,
    CreatePSEPaymentView,
    CreateNequiPaymentView,
    CreateDaviplataPaymentView,
    CreateBancolombiaTransferPaymentView,
    ClientCreditBalanceView,
)

router = DefaultRouter()
router.register(r"admin/credits", ClientCreditAdminViewSet, basename="admin-client-credit")

urlpatterns = [
    # Comisiones del desarrollador
    path("commissions/", CommissionLedgerListView.as_view(), name="commission-ledger-list"),
    path("commissions/<uuid:pk>/", CommissionLedgerDetailView.as_view(), name="commission-ledger-detail"),
    path("commissions/status/", DeveloperCommissionStatusView.as_view(), name="commission-ledger-status"),
    path("commissions/manual-payout/", ManualDeveloperPayoutView.as_view(), name="commission-manual-payout"),

    # Créditos del usuario
    path("credits/balance/", ClientCreditBalanceView.as_view(), name="client-credit-balance"),

    # PSE
    path("pse-banks/", PSEFinancialInstitutionsView.as_view(), name="pse-banks"),

    # Iniciación de pagos (migrado desde spa.views.packages)
    path("payments/appointment/<uuid:pk>/initiate/", InitiateAppointmentPaymentView.as_view(), name="initiate-appointment-payment"),
    path("payments/vip-subscription/initiate/", InitiateVipSubscriptionView.as_view(), name="initiate-vip-subscription"),

    # Webhooks de Wompi (migrado desde spa.views.packages)
    path("webhooks/wompi/", WompiWebhookView.as_view(), name="wompi-webhook"),

    # Compra de paquetes (migrado desde spa.views.packages)
    path("payments/package/initiate/", InitiatePackagePurchaseView.as_view(), name="initiate-package-purchase"),

    # Creación de transacciones server-side por método
    path("payments/<uuid:pk>/pse/", CreatePSEPaymentView.as_view(), name="create-pse-payment"),
    path("payments/<uuid:pk>/nequi/", CreateNequiPaymentView.as_view(), name="create-nequi-payment"),
    path("payments/<uuid:pk>/daviplata/", CreateDaviplataPaymentView.as_view(), name="create-daviplata-payment"),
    path("payments/<uuid:pk>/bancolombia-transfer/", CreateBancolombiaTransferPaymentView.as_view(), name="create-bancolombia-transfer-payment"),

    # Rutas administrativas
    path("", include(router.urls)),
]
