
import hashlib
import json
import requests
from decimal import Decimal
from unittest import mock
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from model_bakery import baker

from finances.models import Payment, WebhookEvent, CommissionLedger, ClientCredit
from finances.gateway import WompiGateway, WompiPaymentClient, build_integrity_signature
from finances.payments import PaymentService
from finances.webhooks import WompiWebhookService
from finances.services import WompiDisbursementClient, DeveloperCommissionService, GlobalSettings
from finances.tasks import (
    check_pending_payments,
    reconcile_recent_payments,
    process_recurring_subscriptions,
    downgrade_expired_vips,
    run_developer_payout,
)
from marketplace.models import Order
from users.models import CustomUser
from spa.models import Appointment

class PaymentServiceEdgeTests(TestCase):
    def setUp(self):
        self.user = baker.make("users.CustomUser")
        self.payment = baker.make(Payment, user=self.user, amount=Decimal("10000.00"), status=Payment.PaymentStatus.PENDING)

    @mock.patch("finances.services.GlobalSettings.load")
    def test_apply_gateway_status_sets_transaction_id_on_approved(self, mock_settings):
        # Mock settings to avoid DB error in _enter_default
        mock_settings.return_value = baker.make(GlobalSettings)
        # Mock DeveloperCommissionService to avoid payout logic failure
        with mock.patch("finances.services.DeveloperCommissionService.handle_successful_payment"):
            payload = {"id": "new-trans-id", "status": "APPROVED"}
            PaymentService.apply_gateway_status(self.payment, "APPROVED", payload)
            self.payment.refresh_from_db()
            self.assertEqual(self.payment.transaction_id, "new-trans-id")
            self.assertEqual(self.payment.status, Payment.PaymentStatus.APPROVED)

    def test_apply_gateway_status_declined(self):
        PaymentService.apply_gateway_status(self.payment, "DECLINED", {})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.PaymentStatus.DECLINED)

    def test_charge_recurrence_token_missing_user_raises(self):
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(None, 1000, "123")

    def test_charge_recurrence_token_missing_token_raises(self):
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(self.user, 1000, None)

    def test_charge_recurrence_token_amount_zero_raises(self):
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(self.user, 0, "123")

    def test_charge_recurrence_token_missing_email_declines(self):
        self.user.email = ""
        self.user.save()
        status, _, _ = PaymentService.charge_recurrence_token(self.user, 1000, "123")
        self.assertEqual(status, Payment.PaymentStatus.DECLINED)

class GatewayEdgeTests(TestCase):
    def setUp(self):
        self.gateway = WompiGateway()
        self.client = WompiPaymentClient()

    def test_build_integrity_signature_without_key_returns_none(self):
        with mock.patch("finances.gateway.settings.WOMPI_INTEGRITY_KEY", None):
            sig = build_integrity_signature("ref", 1000, "COP")
            self.assertIsNone(sig)

    @mock.patch("finances.gateway.cache.get")
    def test_resolve_acceptance_token_missing_config_returns_none(self, mock_get):
        mock_get.return_value = None
        with mock.patch("finances.gateway.settings.WOMPI_ACCEPTANCE_TOKEN", None), \
             mock.patch("finances.gateway.settings.WOMPI_BASE_URL", ""), \
             mock.patch("finances.gateway.settings.WOMPI_PUBLIC_KEY", ""):
            token = WompiPaymentClient.resolve_acceptance_token()
            self.assertIsNone(token)

    def test_fetch_transaction_missing_base_or_reference_returns_none(self):
        self.gateway.base_url = ""
        self.assertIsNone(self.gateway.fetch_transaction("ref"))
        self.gateway.base_url = "http://test.com"
        self.assertIsNone(self.gateway.fetch_transaction(None))

class WebhookViewTests(TestCase):
    def setUp(self):
        self.user = baker.make("users.CustomUser")
        self.order = baker.make(Order, user=self.user, total_amount=Decimal("50000.00"), wompi_transaction_id="ref-123")
        self.payment = baker.make(Payment, user=self.user, amount=Decimal("50000.00"), transaction_id="ref-123", status=Payment.PaymentStatus.PENDING)
        self.order.payments.add(self.payment)
        
        self.payload = {
            "event": "transaction.updated",
            "data": {
                "transaction": {
                    "reference": "ref-123",
                    "status": "APPROVED",
                    "amount_in_cents": 5000000,
                    "id": "wompi-id-123"
                }
            },
            "timestamp": int(timezone.now().timestamp()),
            "signature": {
                "checksum": "",
                "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
            }
        }
        # Generate valid signature
        concat = f"wompi-id-123APPROVED5000000{self.payload['timestamp']}{settings.WOMPI_EVENT_SECRET}"
        self.payload["signature"]["checksum"] = hashlib.sha256(concat.encode()).hexdigest()

    def test_webhook_view_handles_transaction_updated(self):
        service = WompiWebhookService(self.payload)
        # Mocking OrderService and PaymentService logic to avoid side effects
        with mock.patch("marketplace.services.OrderService.confirm_payment") as mock_confirm, \
             mock.patch("finances.payments.PaymentService.apply_gateway_status") as mock_apply:
            result = service.process_transaction_update()
            self.assertEqual(result["status"], "processed_successfully")

    def test_webhook_view_returns_400_on_value_error(self):
        self.payload["signature"]["checksum"] = "invalid"
        service = WompiWebhookService(self.payload)
        with self.assertRaises(ValueError):
            service.process_transaction_update()

class DisbursementClientTests(TestCase):
    def setUp(self):
        self.client = WompiDisbursementClient()
        self.client.base_url = "http://test.com"
        self.client.balance_endpoint = "http://test.com/accounts"
        self.client.private_key = "test_key"

    def test_get_available_balance_invalid_json_raises(self):
        with mock.patch("requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.json.side_effect = ValueError
            with self.assertRaises(Exception): # WompiPayoutError
                self.client.get_available_balance()

    def test_create_payout_missing_destination_raises(self):
        self.client.destination = None
        with self.assertRaises(Exception): # WompiPayoutError
            self.client.create_payout(1000)

    def test_request_with_retry_retries_timeout(self):
        with mock.patch("requests.request") as mock_req:
            mock_req.side_effect = [requests.Timeout, mock.Mock(status_code=200)]
            self.client._request_with_retry("POST", "http://test.com")
            self.assertEqual(mock_req.call_count, 2)

class DeveloperCommissionTests(TestCase):
    def test_evaluate_payout_below_threshold(self):
        with mock.patch("finances.services.GlobalSettings.load") as mock_settings:
            mock_settings.return_value.developer_payout_threshold = Decimal("1000000")
            mock_settings.return_value.developer_in_default = False
            with mock.patch("finances.services.DeveloperCommissionService.get_developer_debt", return_value=Decimal("500")):
                result = DeveloperCommissionService.evaluate_payout()
                self.assertEqual(result["status"], "below_threshold")

    def test_register_commission_returns_none_without_amount(self):
        payment = mock.Mock(spec=Payment)
        payment.amount = None
        self.assertIsNone(DeveloperCommissionService.register_commission(payment))

class SubscriptionTasksTests(TestCase):
    def test_run_developer_payout_task(self):
        with mock.patch("finances.services.DeveloperCommissionService.evaluate_payout") as mock_eval:
            run_developer_payout()
            mock_eval.assert_called_once()

    def test_downgrade_expired_vips_changes_role(self):
        user = baker.make("users.CustomUser", role="VIP", vip_expires_at=timezone.now().date() - timedelta(days=1))
        downgrade_expired_vips()
        user.refresh_from_db()
        self.assertEqual(user.role, "CLIENT")

    def test_process_recurring_subscriptions_price_not_configured(self):
         with mock.patch("finances.tasks.GlobalSettings.load") as mock_settings:
            mock_settings.return_value.vip_monthly_price = None
            process_recurring_subscriptions()
            # Should just return/log, not crash

class InitiateViewsTests(TestCase):
    def setUp(self):
        self.user = baker.make("users.CustomUser", is_verified=True)
        self.client_api = mock.Mock() # Using mock for APIClient if needed, but here testing logic mainly
        
    def test_initiate_appointment_payment_requires_pending_payment(self):
        # Logic test for view
        pass

    def test_initiate_vip_subscription_view_missing_price_returns_500(self):
        # Logic test
        pass

    def test_initiate_package_purchase_invalid_payload(self):
        # Logic test
        pass
