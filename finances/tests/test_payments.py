
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from model_bakery import baker

from finances.payments import PaymentService
from finances.models import Payment

class PaymentServiceTest(TestCase):
    @override_settings(WOMPI_PRIVATE_KEY="pk_test", WOMPI_BASE_URL="https://example.com", WOMPI_CURRENCY="COP")
    def test_charge_recurrence_token_circuit_open(self):
        user = baker.make("users.CustomUser", email="user@test.com")
        
        # Update: Use the cache key defined in WompiPaymentClient
        cache.set("wompi:payments:circuit", {"failures": 5, "open_until": timezone.now() + timedelta(minutes=5)}, timeout=300)

        status, payload, reference = PaymentService.charge_recurrence_token(
            user=user,
            amount=100,
            token="123",
        )

        self.assertEqual(status, Payment.PaymentStatus.DECLINED)
        self.assertIn("Circuito Wompi abierto", payload.get("error", ""))

    @override_settings(
        WOMPI_PRIVATE_KEY="prv_test_123",
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_CURRENCY="COP",
        WOMPI_INTEGRITY_KEY="test_integrity_123",
    )
    @mock.patch("finances.payments.WompiPaymentClient.create_transaction")
    def test_charge_recurrence_token_uses_signature_object(self, mock_create_transaction):
        """La firma de integridad debe enviarse como objeto {'integrity': ...}."""
        cache.delete("wompi:payments:circuit")
        user = baker.make("users.CustomUser", email="user@test.com")

        mock_create_transaction.return_value = (
            {"data": {"status": "APPROVED", "id": "txn-123"}},
            201,
        )

        status, payload, reference = PaymentService.charge_recurrence_token(
            user=user,
            amount=100,
            token="123",
        )

        called_payload = mock_create_transaction.call_args[0][0]
        self.assertIsInstance(called_payload.get("signature"), dict)
        self.assertIn("integrity", called_payload["signature"])
        self.assertEqual(status, Payment.PaymentStatus.APPROVED)

    @mock.patch("finances.payments.WompiPaymentClient.create_transaction")
    def test_charge_recurrence_token_declined(self, mock_create_transaction):
        cache.delete("wompi:payments:circuit")
        user = baker.make("users.CustomUser", email="user@test.com")

        mock_create_transaction.return_value = (
            {"data": {"status": "DECLINED", "id": "txn-123", "status_message": "Insufficient funds"}},
            201,
        )

        status, payload, reference = PaymentService.charge_recurrence_token(
            user=user,
            amount=100,
            token="123",
        )

        self.assertEqual(status, Payment.PaymentStatus.DECLINED)
        self.assertEqual(payload["status"], "DECLINED")

    @mock.patch("finances.payments.WompiPaymentClient.create_transaction")
    def test_charge_recurrence_token_error(self, mock_create_transaction):
        cache.delete("wompi:payments:circuit")
        user = baker.make("users.CustomUser", email="user@test.com")

        mock_create_transaction.return_value = (
            {"error": "Gateway error"},
            500,
        )

        status, payload, reference = PaymentService.charge_recurrence_token(
            user=user,
            amount=100,
            token="123",
        )

        self.assertEqual(status, Payment.PaymentStatus.DECLINED)
        self.assertIn("error", payload)
