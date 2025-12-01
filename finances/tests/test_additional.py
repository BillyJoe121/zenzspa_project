from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker

from finances.gateway import WompiGateway, WompiPaymentClient
from finances.models import (
    Payment,
    CommissionLedger,
    PaymentToken,
    WebhookEvent,
)
from finances.payments import PaymentService
from finances.subscriptions import VipMembershipService, VipSubscriptionService
from finances.tasks import (
    check_pending_payments,
    cleanup_old_webhook_events,
)
from finances.webhooks import WompiWebhookService
from finances.views import PSEFinancialInstitutionsView, WompiWebhookView
from rest_framework.test import APIRequestFactory, force_authenticate
from users.models import CustomUser


class PaymentServiceUtilsTests(TestCase):
    def test_build_tax_payload_includes_vat_and_consumption(self):
        payment = baker.make(
            Payment,
            tax_vat_in_cents=1900,
            tax_consumption_in_cents=500,
        )
        payload = PaymentService._build_tax_payload(payment)
        self.assertEqual(payload["vat"], 1900)
        self.assertEqual(payload["consumption"], 500)

    def test_build_customer_data_uses_user_info(self):
        user = baker.make(CustomUser, first_name="Ana", last_name="Lopez", phone_number="3011234567")
        payment = baker.make(
            Payment,
            customer_legal_id="123456789",
            customer_legal_id_type="CC",
            user=user,
        )
        data = PaymentService._build_customer_data(payment)
        self.assertEqual(data["legal_id"], "123456789")
        self.assertEqual(data["legal_id_type"], "CC")
        self.assertIn("Ana", data["full_name"])
        self.assertEqual(data["phone_number"], "3011234567")

    def test_poll_pending_payment_sets_timeout_without_transaction_id(self):
        payment = baker.make(Payment, status=Payment.PaymentStatus.PENDING, transaction_id="")
        result = PaymentService.poll_pending_payment(payment)
        payment.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(payment.status, Payment.PaymentStatus.TIMEOUT)

    @override_settings(WOMPI_CURRENCY="COP")
    @mock.patch("finances.payments.WompiPaymentClient.create_pse_transaction")
    def test_create_pse_payment_updates_fields(self, mock_pse):
        mock_pse.return_value = ({"data": {"payment_method": {"extra": {"async_payment_url": "http://a.com"}}}}, 201)
        payment = baker.make(Payment, status=Payment.PaymentStatus.PENDING, amount=Decimal("100.00"), user__email="test@example.com")
        PaymentService.create_pse_payment(
            payment=payment,
            user_type=0,
            user_legal_id="123",
            user_legal_id_type="CC",
            financial_institution_code="1",
            payment_description="Pago",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.payment_method_type, "PSE")
        self.assertEqual(payment.payment_method_data.get("financial_institution_code"), "1")
        self.assertIn("async_payment_url", payment.payment_method_data)
        self.assertEqual(payment.customer_legal_id, "123")
        self.assertEqual(payment.customer_legal_id_type, "CC")


class WebhookServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    @mock.patch.object(WompiWebhookService, "_validate_signature", return_value=None)
    def test_process_token_update_creates_payment_token(self, _):
        payload = {
            "event": "nequi_token.updated",
            "data": {
                "token": {"id": "tok_nequi_abc", "status": "APPROVED", "phone_number": "3991111111"}
            },
            "signature": {"checksum": "dummy", "properties": ["data.id"]},
            "timestamp": int(timezone.now().timestamp()),
        }
        service = WompiWebhookService(payload, headers={})
        result = service.process_token_update()
        token = PaymentToken.objects.get(token_id="tok_nequi_abc")
        self.assertEqual(result["token_status"], "APPROVED")
        self.assertEqual(token.status, "APPROVED")

    @mock.patch.object(WompiWebhookService, "_validate_signature", return_value=None)
    def test_process_payout_update_updates_commission_ledger(self, _):
        ledger = baker.make(
            CommissionLedger,
            wompi_transfer_id="TRF123",
            status=CommissionLedger.Status.PENDING,
            amount=Decimal("10.00"),
        )
        payload = {
            "event": "transfer.updated",
            "data": {"transfer": {"id": "TRF123", "status": "APPROVED"}},
            "signature": {"checksum": "dummy", "properties": ["data.id"]},
            "timestamp": int(timezone.now().timestamp()),
        }
        service = WompiWebhookService(payload, headers={})
        result = service.process_payout_update()
        ledger.refresh_from_db()
        self.assertEqual(ledger.status, CommissionLedger.Status.PAID)
        self.assertEqual(result["entries_updated"], 1)


class ViewsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        cache.clear()

    @mock.patch("finances.views.WompiPaymentClient.get_pse_financial_institutions")
    def test_pse_financial_institutions_http_error(self, mock_get):
        response_obj = mock.Mock()
        response_obj.status_code = 503
        http_error = requests.HTTPError(response=response_obj)
        mock_get.side_effect = http_error
        request = self.factory.get("/api/finances/pse-banks/")
        force_authenticate(request, user=baker.make(CustomUser))
        response = PSEFinancialInstitutionsView.as_view()(request)
        self.assertEqual(response.status_code, 503)

    def test_webhook_view_unhandled_event(self):
        payload = {"event": "unknown.event", "signature": {"checksum": "c", "properties": ["data"]}, "timestamp": int(timezone.now().timestamp()), "data": {}}
        request = self.factory.post("/api/finances/webhooks/wompi/", payload, format="json")
        response = WompiWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), "event_type_not_handled")


class SubscriptionsTests(TestCase):
    def test_extend_membership_sets_dates(self):
        user = baker.make(CustomUser, role=CustomUser.Role.CLIENT, vip_expires_at=None, vip_active_since=None)
        start, end = VipMembershipService.extend_membership(user, months=1)
        user.refresh_from_db()
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(user.role, CustomUser.Role.VIP)

    def test_extend_membership_invalid_months(self):
        user = baker.make(CustomUser)
        start, end = VipMembershipService.extend_membership(user, months=0)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_fulfill_subscription_creates_log(self):
        payment = baker.make(Payment, user=baker.make(CustomUser))
        VipSubscriptionService.fulfill_subscription(payment, months=1)
        user = payment.user
        user.refresh_from_db()
        self.assertTrue(user.vip_auto_renew)
        self.assertEqual(user.vip_failed_payments, 0)
        self.assertTrue(user.subscription_logs.exists())


class TasksTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    @mock.patch("finances.tasks.PaymentService.poll_pending_payment")
    def test_check_pending_payments_counts(self, mock_poll):
        old_payment = baker.make(
            Payment,
            status=Payment.PaymentStatus.PENDING,
            created_at=timezone.now() - timedelta(minutes=20),
        )
        result = check_pending_payments()
        self.assertIn("Pagos pendientes revisados", result)
        mock_poll.assert_called_once_with(old_payment)

    def test_cleanup_old_webhook_events_deletes(self):
        ninety_one_days_ago = timezone.now() - timedelta(days=91)
        one_eighty_one_days_ago = timezone.now() - timedelta(days=181)
        baker.make(WebhookEvent, status=WebhookEvent.Status.PROCESSED, created_at=ninety_one_days_ago)
        baker.make(WebhookEvent, status=WebhookEvent.Status.FAILED, created_at=one_eighty_one_days_ago)
        result = cleanup_old_webhook_events()
        self.assertGreaterEqual(result["total_deleted"], 2)


class GatewayCircuitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_create_transaction_circuit_open_raises(self):
        cache.set("wompi:payments:circuit", {"failures": 0, "open_until": timezone.now() + timedelta(minutes=5)}, timeout=300)
        client = WompiPaymentClient()
        with self.assertRaises(requests.RequestException):
            client.create_transaction({"reference": "X"})

    def test_fetch_transaction_circuit_open_returns_none(self):
        cache.set("wompi:transactions:circuit", {"failures": 0, "open_until": timezone.now() + timedelta(minutes=5)}, timeout=300)
        gw = WompiGateway()
        result = gw.fetch_transaction("REF-1")
        self.assertIsNone(result)
