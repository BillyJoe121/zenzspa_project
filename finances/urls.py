from django.urls import path

from .views import CommissionLedgerListView, DeveloperCommissionStatusView

urlpatterns = [
    path("commissions/", CommissionLedgerListView.as_view(), name="commission-ledger-list"),
    path("commissions/status/", DeveloperCommissionStatusView.as_view(), name="commission-ledger-status"),
]
