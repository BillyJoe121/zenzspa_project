import json
import pytest
from django.utils import timezone
from model_bakery import baker

from spa.services import WompiWebhookService
from spa.models import Payment


def _build_signature(payload_data, timestamp, secret):
    body_str = json.dumps(payload_data, separators=(",", ":"))
    concat = f"{body_str}{timestamp}{secret}"
    import hashlib
    return hashlib.sha256(concat.encode("utf-8")).hexdigest()


@pytest.mark.django_db
def test_webhook_rejects_amount_mismatch(settings):
    settings.WOMPI_EVENT_SECRET = "testsecret"
    payment = baker.make(
        Payment,
        amount=100,
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.ADVANCE,
        transaction_id="REF-123",
    )

    transaction = {
        "reference": "REF-123",
        "status": "APPROVED",
        "amount_in_cents": 10,  # incorrect
    }
    timestamp = int(timezone.now().timestamp())
    data = {"transaction": transaction}
    signature = _build_signature(data, timestamp, settings.WOMPI_EVENT_SECRET)
    payload = {
        "data": data,
        "event": "transaction.updated",
        "signature": {"checksum": signature},
        "timestamp": timestamp,
    }

    service = WompiWebhookService(payload, headers={})
    result = service.process_transaction_update()

    payment.refresh_from_db()
    assert result["status"] == "amount_mismatch"
    assert payment.status == Payment.PaymentStatus.ERROR
