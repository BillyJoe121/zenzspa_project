import pytest
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from model_bakery import baker

from spa.services import PaymentService
from spa.models import Payment


@pytest.mark.django_db
def test_charge_recurrence_token_circuit_open(settings):
    settings.WOMPI_PRIVATE_KEY = "pk_test"
    settings.WOMPI_BASE_URL = "https://example.com"
    settings.WOMPI_CURRENCY = "COP"
    user = baker.make("users.CustomUser", email="user@test.com")

    cache.set("wompi:circuit", {"failures": 5, "open_until": timezone.now() + timedelta(minutes=5)}, timeout=300)

    status, payload, reference = PaymentService.charge_recurrence_token(
        user=user,
        amount=100,
        token="123",
    )

    assert status == Payment.PaymentStatus.DECLINED
    assert payload.get("error") == "circuit_open"
