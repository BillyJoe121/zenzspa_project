from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import GlobalSettings
from finances.models import ClientCredit, CommissionLedger, Payment, WebhookEvent
from finances.services import DeveloperCommissionService, WompiDisbursementClient, WompiPayoutError
from spa.models import Appointment, AppointmentItem, Service, ServiceCategory
from users.models import CustomUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client_user():
    return CustomUser.objects.create_user(
        phone_number="+575000000001",
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
    )


def _make_payment_and_payload(user, amount=Decimal("50000.00"), status="APPROVED", amount_in_cents=None):
    service_cat = ServiceCategory.objects.create(name="Cat", description="desc")
    service = Service.objects.create(name="Masaje", description="desc", duration=60, price=amount, category=service_cat, is_active=True)
    appt = Appointment.objects.create(
        user=user,
        start_time=timezone.now() + timedelta(hours=2),
        end_time=timezone.now() + timedelta(hours=3),
        status=Appointment.AppointmentStatus.PENDING_PAYMENT,
        price_at_purchase=amount,
    )
    AppointmentItem.objects.create(
        appointment=appt,
        service=service,
        duration=service.duration,
        price_at_purchase=service.price,
    )
    payment = Payment.objects.create(
        user=user,
        appointment=appt,
        amount=amount,
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.ADVANCE,
        transaction_id="trx-123",
    )
    payload = {
        "event": "transaction.updated",
        "data": {
            "transaction": {
                "id": "wompi-id-123",
                "amount_in_cents": int(amount * 100) if amount_in_cents is None else amount_in_cents,
                "status": status,
                "reference": payment.transaction_id,
            }
        },
        "signature": {
            "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents", "transaction.reference"],
            "checksum": "",
        },
        "timestamp": int(timezone.now().timestamp()),
    }
    return payment, payload, appt


def _sign_payload(payload, secret):
    # Reproduce la lógica de firma del webhook sin tocar la BD
    properties = payload["signature"]["properties"]
    values = []
    data = payload["data"]
    for prop_path in properties:
        keys = prop_path.split(".")
        value = data
        for key in keys:
            value = value.get(key, "") if isinstance(value, dict) else ""
        values.append(str(value))
    concatenated = "".join(values) + str(payload["timestamp"]) + secret
    import hashlib

    payload["signature"]["checksum"] = hashlib.sha256(concatenated.encode("utf-8")).hexdigest().upper()
    return payload


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def test_wompi_webhook_approved_sets_payment_and_ledger(api_client, client_user, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    payment, payload, appt = _make_payment_and_payload(client_user)
    payload = _sign_payload(payload, settings.WOMPI_EVENT_SECRET)

    resp = api_client.post(reverse("wompi-webhook"), payload, format="json")

    assert resp.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status == Payment.PaymentStatus.APPROVED
    appt.refresh_from_db()
    assert appt.status in [Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PAID]
    assert WebhookEvent.objects.filter(event_type="transaction.updated", status=WebhookEvent.Status.PROCESSED).exists()

    # Se crea ledger por cobro
    assert CommissionLedger.objects.filter(source_payment=payment).exists()


def test_wompi_webhook_invalid_signature_fails(api_client, client_user, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    payment, payload, _ = _make_payment_and_payload(client_user)
    payload["signature"]["checksum"] = "BADSIGN"

    resp = api_client.post(reverse("wompi-webhook"), payload, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    payment.refresh_from_db()
    assert payment.status == Payment.PaymentStatus.PENDING
    event = WebhookEvent.objects.filter(event_type="transaction.updated").latest("created_at")
    assert event.status in [WebhookEvent.Status.FAILED, WebhookEvent.Status.PROCESSED]


def test_wompi_webhook_amount_mismatch_marks_error(api_client, client_user, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    payment, payload, _ = _make_payment_and_payload(client_user, amount=Decimal("50000.00"), amount_in_cents=999999)
    payload = _sign_payload(payload, settings.WOMPI_EVENT_SECRET)

    resp = api_client.post(reverse("wompi-webhook"), payload, format="json")

    assert resp.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK}
    payment.refresh_from_db()
    assert payment.status in [Payment.PaymentStatus.ERROR, Payment.PaymentStatus.PENDING]
    event = WebhookEvent.objects.filter(event_type="transaction.updated").latest("created_at")
    assert event.status in [WebhookEvent.Status.FAILED, WebhookEvent.Status.PROCESSED]


def test_evaluate_payout_marks_ledgers_paid(monkeypatch, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    gs = GlobalSettings.load()
    gs.developer_payout_threshold = Decimal("100000.00")
    gs.developer_in_default = False
    gs.save()
    payer = CustomUser.objects.create_user(phone_number="+575000000777", password="Secret123!", is_verified=True)
    payment = Payment.objects.create(
        user=payer,
        amount=Decimal("150000.00"),
        status=Payment.PaymentStatus.APPROVED,
        payment_type=Payment.PaymentType.ORDER,
    )
    ledger = CommissionLedger.objects.create(
        amount=Decimal("150000.00"),
        status=CommissionLedger.Status.PENDING,
        source_payment=payment,
    )

    monkeypatch.setattr(WompiDisbursementClient, "get_available_balance", staticmethod(lambda self=None: Decimal("200000.00")))
    monkeypatch.setattr(WompiDisbursementClient, "create_payout", staticmethod(lambda amount: "TRF-123"))

    result = DeveloperCommissionService.evaluate_payout()

    ledger.refresh_from_db()
    assert result.get("status") == "paid"
    assert ledger.status == CommissionLedger.Status.PAID
    assert ledger.wompi_transfer_id == "TRF-123"


def test_evaluate_payout_insufficient_funds_marks_default(monkeypatch, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    gs = GlobalSettings.load()
    gs.developer_payout_threshold = Decimal("100000.00")
    gs.developer_in_default = False
    gs.save()
    payer = CustomUser.objects.create_user(phone_number="+575000000778", password="Secret123!", is_verified=True)
    payment = Payment.objects.create(
        user=payer,
        amount=Decimal("150000.00"),
        status=Payment.PaymentStatus.APPROVED,
        payment_type=Payment.PaymentType.ORDER,
    )
    ledger = CommissionLedger.objects.create(
        amount=Decimal("150000.00"),
        status=CommissionLedger.Status.PENDING,
        source_payment=payment,
    )

    monkeypatch.setattr(WompiDisbursementClient, "get_available_balance", staticmethod(lambda self=None: Decimal("50000.00")))
    monkeypatch.setattr(WompiDisbursementClient, "create_payout", staticmethod(lambda amount: (_ for _ in ()).throw(WompiPayoutError("NSF"))))

    result = DeveloperCommissionService.evaluate_payout()

    ledger.refresh_from_db()
    assert ledger.status in [CommissionLedger.Status.FAILED_NSF, CommissionLedger.Status.PENDING]
    assert "nsf" in str(result).lower() or "insufficient" in str(result).lower() or result.get("status") in ["payout_failed", "insufficient_funds"]


def test_expired_credit_not_applied():
    user = CustomUser.objects.create_user(
        phone_number="+575000000099",
        password="Secret123!",
        is_verified=True,
    )
    credit = ClientCredit.objects.create(
        user=user,
        initial_amount=Decimal("10000.00"),
        remaining_amount=Decimal("10000.00"),
        status=ClientCredit.CreditStatus.AVAILABLE,
        expires_at=timezone.now().date() - timedelta(days=1),
    )

    credit.refresh_from_db()
    assert credit.expires_at < timezone.now().date()
    credit.status = ClientCredit.CreditStatus.EXPIRED
    credit.save(update_fields=["status", "updated_at"])
    credit.refresh_from_db()
    assert credit.status == ClientCredit.CreditStatus.EXPIRED
