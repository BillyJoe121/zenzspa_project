from django.urls import path

from .views import (
    CommissionLedgerListView,
    DeveloperCommissionStatusView,
    PSEFinancialInstitutionsView,
)

urlpatterns = [
    path("commissions/", CommissionLedgerListView.as_view(), name="commission-ledger-list"),
    path("commissions/status/", DeveloperCommissionStatusView.as_view(), name="commission-ledger-status"),
    path("pse-banks/", PSEFinancialInstitutionsView.as_view(), name="pse-banks"),
]
