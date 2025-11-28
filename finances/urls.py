"""
URLs para el módulo finances.
"""
from django.urls import path

from .views import (
    CommissionLedgerListView,
    DeveloperCommissionStatusView,
    PSEFinancialInstitutionsView,
    InitiateAppointmentPaymentView,
    WompiWebhookView,
    InitiateVipSubscriptionView,
    InitiatePackagePurchaseView,
)

urlpatterns = [
    # Comisiones del desarrollador
    path("commissions/", CommissionLedgerListView.as_view(), name="commission-ledger-list"),
    path("commissions/status/", DeveloperCommissionStatusView.as_view(), name="commission-ledger-status"),

    # PSE
    path("pse-banks/", PSEFinancialInstitutionsView.as_view(), name="pse-banks"),

    # Iniciación de pagos (migrado desde spa.views.packages)
    path("payments/appointment/<uuid:pk>/initiate/", InitiateAppointmentPaymentView.as_view(), name="initiate-appointment-payment"),
    path("payments/vip-subscription/initiate/", InitiateVipSubscriptionView.as_view(), name="initiate-vip-subscription"),

    # Webhooks de Wompi (migrado desde spa.views.packages)
    path("webhooks/wompi/", WompiWebhookView.as_view(), name="wompi-webhook"),

    # Compra de paquetes (migrado desde spa.views.packages)
    path("payments/package/initiate/", InitiatePackagePurchaseView.as_view(), name="initiate-package-purchase"),
]
