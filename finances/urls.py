"""
URLs para el módulo finances.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientCreditAdminViewSet,
    CommissionLedgerListView,
    CommissionLedgerDetailView,
    CommissionBreakdownByTypeView,
    CommissionBreakdownByMethodView,
    DeveloperCommissionStatusView,
    ManualDeveloperPayoutView,
    PSEFinancialInstitutionsView,
    InitiateAppointmentPaymentView,
    WompiWebhookView,
    WompiManualConfirmView,
    InitiateVipSubscriptionView,
    InitiatePackagePurchaseView,
    CreatePSEPaymentView,
    CreateNequiPaymentView,
    CreateDaviplataPaymentView,
    CreateBancolombiaTransferPaymentView,
    ClientCreditBalanceView,
    # Wompi Payouts API
    WompiPayoutsAccountsView,
    WompiPayoutsBanksView,
    WompiPayoutsBalanceView,
    WompiPayoutsRechargeView,
    WompiPayoutsWebhookView,
)

router = DefaultRouter()
router.register(r"admin/credits", ClientCreditAdminViewSet, basename="admin-client-credit")

urlpatterns = [
    # Comisiones del desarrollador
    path("commissions/", CommissionLedgerListView.as_view(), name="commission-ledger-list"),
    path("commissions/<uuid:pk>/", CommissionLedgerDetailView.as_view(), name="commission-ledger-detail"),
    path("commissions/breakdown-by-type/", CommissionBreakdownByTypeView.as_view(), name="commission-breakdown-by-type"),
    path("commissions/breakdown-by-method/", CommissionBreakdownByMethodView.as_view(), name="commission-breakdown-by-method"),
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
    path("webhooks/wompi/manual-confirm/", WompiManualConfirmView.as_view(), name="wompi-manual-confirm"),

    # Compra de paquetes (migrado desde spa.views.packages)
    path("payments/package/initiate/", InitiatePackagePurchaseView.as_view(), name="initiate-package-purchase"),

    # Creación de transacciones server-side por método
    path("payments/<uuid:pk>/pse/", CreatePSEPaymentView.as_view(), name="create-pse-payment"),
    path("payments/<uuid:pk>/nequi/", CreateNequiPaymentView.as_view(), name="create-nequi-payment"),
    path("payments/<uuid:pk>/daviplata/", CreateDaviplataPaymentView.as_view(), name="create-daviplata-payment"),
    path("payments/<uuid:pk>/bancolombia-transfer/", CreateBancolombiaTransferPaymentView.as_view(), name="create-bancolombia-transfer-payment"),

    # Wompi Payouts API (Admin/Staff only)
    path("wompi-payouts/accounts/", WompiPayoutsAccountsView.as_view(), name="wompi-payouts-accounts"),
    path("wompi-payouts/banks/", WompiPayoutsBanksView.as_view(), name="wompi-payouts-banks"),
    path("wompi-payouts/balance/", WompiPayoutsBalanceView.as_view(), name="wompi-payouts-balance"),
    path("wompi-payouts/sandbox/recharge/", WompiPayoutsRechargeView.as_view(), name="wompi-payouts-sandbox-recharge"),
    path("wompi-payouts/webhook/", WompiPayoutsWebhookView.as_view(), name="wompi-payouts-webhook"),

    # Rutas administrativas
    path("", include(router.urls)),
]
