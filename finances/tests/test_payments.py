from datetime import timedelta
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
