from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIRequestFactory, force_authenticate

from finances.gateway import WompiGateway, WompiPaymentClient, build_integrity_signature
from finances.models import Payment, WebhookEvent
from finances.payments import PaymentService
from finances.services import DeveloperCommissionService, WompiDisbursementClient, WompiPayoutError
from finances.subscriptions import VipMembershipService
from finances.tasks import process_recurring_subscriptions, downgrade_expired_vips, run_developer_payout
from finances.views import (
    WompiWebhookView,
    InitiateVipSubscriptionView,
    InitiateAppointmentPaymentView,
    InitiatePackagePurchaseView,
)


class PaymentServiceEdgeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_charge_recurrence_token_missing_user_raises(self):
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(user=None, amount=100, token="1")

    def test_charge_recurrence_token_missing_token_raises(self):
        user = baker.make("users.CustomUser", email="test@example.com")
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(user=user, amount=100, token=None)

    def test_charge_recurrence_token_amount_zero_raises(self):
        user = baker.make("users.CustomUser", email="test@example.com")
        with self.assertRaises(ValueError):
            PaymentService.charge_recurrence_token(user=user, amount=0, token="123")

    def test_charge_recurrence_token_missing_email_declines(self):
        user = baker.make("users.CustomUser", email="")
        status, payload, reference = PaymentService.charge_recurrence_token(user=user, amount=100, token="123")
        self.assertEqual(status, Payment.PaymentStatus.DECLINED)
        self.assertIn("missing_email", payload.get("error", ""))

    def test_apply_gateway_status_sets_transaction_id_on_approved(self):
        payment = baker.make(Payment, status=Payment.PaymentStatus.PENDING, transaction_id="")
        payload = {"id": "TRX123"}
        PaymentService.apply_gateway_status(payment, "APPROVED", payload)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PaymentStatus.APPROVED)
        self.assertEqual(payment.transaction_id, "TRX123")

    def test_apply_gateway_status_declined(self):
        payment = baker.make(Payment, status=Payment.PaymentStatus.PENDING)
        PaymentService.apply_gateway_status(payment, "DECLINED", {"status": "DECLINED"})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PaymentStatus.DECLINED)


class GatewayEdgeTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(WOMPI_INTEGRITY_KEY=None)
    def test_build_integrity_signature_without_key_returns_none(self):
        sig = build_integrity_signature("REF", 100, "COP")
        self.assertIsNone(sig)

    @override_settings(WOMPI_BASE_URL="", WOMPI_PUBLIC_KEY="")
    def test_resolve_acceptance_token_missing_config_returns_none(self):
        token = WompiPaymentClient.resolve_acceptance_token(base_url="", public_key="")
        self.assertIsNone(token)

    def test_fetch_transaction_missing_base_or_reference_returns_none(self):
        gw = WompiGateway(base_url="", private_key="x")
        result = gw.fetch_transaction(reference="ABC")
        self.assertIsNone(result)


class DisbursementClientTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_available_balance_invalid_json_raises(self):
        client = WompiDisbursementClient()
        response = mock.Mock()
        response.json.side_effect = ValueError("bad json")
        response.raise_for_status.return_value = None
        with mock.patch("finances.services.requests.request", return_value=response):
            with self.assertRaises(WompiPayoutError):
                client.get_available_balance()

    def test_create_payout_missing_destination_raises(self):
        client = WompiDisbursementClient()
        with self.assertRaises(WompiPayoutError):
            client.create_payout(Decimal("10.00"))

    def test_request_with_retry_retries_timeout(self):
        client = WompiDisbursementClient()
        success_response = mock.Mock()
        success_response.raise_for_status.return_value = None
        with mock.patch("finances.services.requests.request", side_effect=[requests.Timeout, success_response]) as mock_req, \
                mock.patch("time.sleep") as mock_sleep:
            result = client._request_with_retry("get", "http://example.com")
            self.assertEqual(result, success_response)
            self.assertEqual(mock_req.call_count, 2)
            mock_sleep.assert_called_once()


class DeveloperCommissionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_commission_returns_none_without_amount(self):
        payment = baker.make(Payment, amount=Decimal("0.00"))
        result = DeveloperCommissionService.register_commission(payment)
        self.assertIsNone(result)

    @mock.patch("finances.services.GlobalSettings.load")
    def test_evaluate_payout_below_threshold(self, mock_load):
        settings_obj = mock.Mock()
        settings_obj.developer_payout_threshold = Decimal("1000.00")
        settings_obj.developer_in_default = False
        mock_load.return_value = settings_obj
        with mock.patch.object(DeveloperCommissionService, "get_developer_debt", return_value=Decimal("10.00")):
            result = DeveloperCommissionService.evaluate_payout()
            self.assertEqual(result["status"], "below_threshold")


class SubscriptionTasksTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    @mock.patch("finances.tasks.GlobalSettings.load")
    def test_process_recurring_subscriptions_price_not_configured(self, mock_load):
        settings_obj = mock.Mock()
        settings_obj.vip_monthly_price = None
        mock_load.return_value = settings_obj
        result = process_recurring_subscriptions()
        self.assertIn("Precio VIP no configurado", result)

    def test_downgrade_expired_vips_changes_role(self):
        expired = baker.make(
            "users.CustomUser",
            role="VIP",
            vip_expires_at=timezone.now().date() - timedelta(days=1),
            vip_auto_renew=True,
            vip_failed_payments=2,
        )
        result = downgrade_expired_vips()
        expired.refresh_from_db()
        self.assertEqual(expired.role, expired.Role.CLIENT)
        self.assertFalse(expired.vip_auto_renew)
        self.assertIn("Usuarios degradados", result)

    @mock.patch.object(DeveloperCommissionService, "evaluate_payout", return_value={"status": "paid"})
    def test_run_developer_payout_task(self, mock_eval):
        result = run_developer_payout()
        mock_eval.assert_called_once()
        self.assertEqual(result["status"], "paid")


class WebhookViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        cache.clear()

    @mock.patch("finances.views.WompiWebhookService.process_transaction_update", side_effect=ValueError("bad sig"))
    def test_webhook_view_returns_400_on_value_error(self, mock_process):
        payload = {"event": "transaction.updated", "signature": {"checksum": "c", "properties": ["data"]}, "timestamp": int(timezone.now().timestamp()), "data": {}}
        request = self.factory.post("/api/finances/webhooks/wompi/", payload, format="json")
        response = WompiWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    @mock.patch("finances.views.WompiWebhookService.process_transaction_update", return_value={"status": "ok"})
    def test_webhook_view_handles_transaction_updated(self, mock_process):
        payload = {"event": "transaction.updated", "signature": {"checksum": "c", "properties": ["data"]}, "timestamp": int(timezone.now().timestamp()), "data": {}}
        request = self.factory.post("/api/finances/webhooks/wompi/", payload, format="json")
        response = WompiWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), "webhook processed")


class InitiateViewsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        cache.clear()
        self.user = baker.make("users.CustomUser", is_verified=True)

    def _disable_permissions(self, view_cls):
        original = view_cls.permission_classes
        view_cls.permission_classes = []
        return original

    def test_initiate_vip_subscription_view_missing_price_returns_500(self):
        with mock.patch("finances.views.GlobalSettings.load") as mock_load:
            settings_obj = mock.Mock()
            settings_obj.vip_monthly_price = None
            mock_load.return_value = settings_obj
            request = self.factory.post("/api/finances/payments/vip-subscription/initiate/")
            force_authenticate(request, user=self.user)
            original = self._disable_permissions(InitiateVipSubscriptionView)
            response = InitiateVipSubscriptionView.as_view()(request)
            InitiateVipSubscriptionView.permission_classes = original
            self.assertEqual(response.status_code, 500)

    def test_initiate_appointment_payment_requires_pending_payment(self):
        appointment = baker.make("spa.Appointment", user=self.user, status="PENDING_PAYMENT")
        request = self.factory.get(f"/api/finances/payments/appointment/{appointment.id}/initiate/")
        force_authenticate(request, user=self.user)
        # appointment has no pending payment -> should 404
        original = self._disable_permissions(InitiateAppointmentPaymentView)
        response = InitiateAppointmentPaymentView.as_view()(request, pk=appointment.id)
        InitiateAppointmentPaymentView.permission_classes = original
        self.assertEqual(response.status_code, 404)

    def test_initiate_package_purchase_invalid_payload(self):
        request = self.factory.post("/api/finances/payments/package/initiate/", data={})
        force_authenticate(request, user=self.user)
        original = self._disable_permissions(InitiatePackagePurchaseView)
        response = InitiatePackagePurchaseView.as_view()(request)
        InitiatePackagePurchaseView.permission_classes = original
        self.assertEqual(response.status_code, 400)
