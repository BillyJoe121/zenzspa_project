"""
Views del módulo finances.

Este paquete divide las views en módulos por dominio:
- commissions: Gestión de comisiones del desarrollador
- payments: Iniciación de pagos (appointments, VIP, packages)
- webhooks: Webhook de Wompi
- credits: Créditos de cliente y pagos
- payouts: Wompi Payouts API
- analytics: Analytics de finanzas (servicios + marketplace)

Todas las views se re-exportan aquí para mantener compatibilidad con urls.py
"""

# Comisiones del desarrollador
from .commissions import (
    CommissionLedgerListView,
    CommissionLedgerDetailView,
    CommissionBreakdownByTypeView,
    CommissionBreakdownByMethodView,
    DeveloperCommissionStatusView,
    ManualDeveloperPayoutView,
)

# Iniciación de pagos
from .payments import (
    PSEFinancialInstitutionsView,
    InitiateAppointmentPaymentView,
    InitiateVipSubscriptionView,
    InitiatePackagePurchaseView,
    BasePaymentCreationView,
    CreatePSEPaymentView,
    CreateNequiPaymentView,
    CreateDaviplataPaymentView,
    CreateBancolombiaTransferPaymentView,
)

# Webhooks de Wompi
from .webhooks import (
    WompiWebhookView,
    WompiManualConfirmView,
)

# Créditos de cliente
from .credits import (
    ClientCreditAdminViewSet,
    ClientCreditViewSet,
    PaymentHistoryView,
    ClientCreditBalanceView,
    CreditPaymentPreviewView,
)

# Wompi Payouts API
from .payouts import (
    WompiPayoutsAccountsView,
    WompiPayoutsBanksView,
    WompiPayoutsBalanceView,
    WompiPayoutsRechargeView,
    WompiPayoutsWebhookView,
)

# Analytics de Finanzas - Servicios
from .analytics import (
    ServicesRevenueView,
    ServicesCompletedAppointmentsView,
    ServicesStatusDistributionView,
    MarketplaceRevenueView,
    MarketplaceProductsRevenueView,
    MarketplaceOrdersStatsView,
    MarketplaceDailyRevenueView,
)

# Reexports para compatibilidad con tests (patch a nivel módulo)
from finances.gateway import WompiPaymentClient
from finances.payments import PaymentService
from finances.services import DeveloperCommissionService, WompiDisbursementClient
from finances.webhooks import WompiWebhookService


__all__ = [
    # Comisiones
    "CommissionLedgerListView",
    "CommissionLedgerDetailView",
    "CommissionBreakdownByTypeView",
    "CommissionBreakdownByMethodView",
    "DeveloperCommissionStatusView",
    "ManualDeveloperPayoutView",
    # Pagos
    "PSEFinancialInstitutionsView",
    "InitiateAppointmentPaymentView",
    "InitiateVipSubscriptionView",
    "InitiatePackagePurchaseView",
    "BasePaymentCreationView",
    "CreatePSEPaymentView",
    "CreateNequiPaymentView",
    "CreateDaviplataPaymentView",
    "CreateBancolombiaTransferPaymentView",
    # Webhooks
    "WompiWebhookView",
    "WompiManualConfirmView",
    # Créditos
    "ClientCreditAdminViewSet",
    "ClientCreditViewSet",
    "PaymentHistoryView",
    "ClientCreditBalanceView",
    "CreditPaymentPreviewView",
    # Payouts
    "WompiPayoutsAccountsView",
    "WompiPayoutsBanksView",
    "WompiPayoutsBalanceView",
    "WompiPayoutsRechargeView",
    "WompiPayoutsWebhookView",
    # Analytics - Servicios
    "ServicesRevenueView",
    "ServicesCompletedAppointmentsView",
    "ServicesStatusDistributionView",
    # Analytics - Marketplace
    "MarketplaceRevenueView",
    "MarketplaceProductsRevenueView",
    "MarketplaceOrdersStatsView",
    "MarketplaceDailyRevenueView",
    "WompiPaymentClient",
    "PaymentService",
    "DeveloperCommissionService",
    "WompiDisbursementClient",
    "WompiWebhookService",
]
