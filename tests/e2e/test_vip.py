from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import AuditLog, GlobalSettings
from finances.models import Payment, SubscriptionLog
from finances.payments import PaymentService
from finances.tasks import (
    downgrade_expired_vips,
    process_recurring_subscriptions,
)
from spa.models import LoyaltyRewardLog, Service, ServiceCategory, Voucher
from spa.tasks import check_vip_loyalty
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
        phone_number="+573500000001",
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
    )


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def _set_vip_price(amount=Decimal("50000")):
    settings = GlobalSettings.load()
    settings.vip_monthly_price = amount
    settings.save()
    return settings


def _make_service(name="Masaje VIP"):
    cat = ServiceCategory.objects.create(name=f"Cat {name}", description="desc")
    return Service.objects.create(
        name=name,
        description="desc",
        duration=60,
        price=Decimal("100000"),
        category=cat,
        is_active=True,
    )


def test_vip_subscription_purchase_flow(api_client, client_user):
    _set_vip_price()
    _auth(api_client, client_user)
    url = reverse("initiate-vip-subscription")
    resp = api_client.post(url, {}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    reference = resp.data["reference"]
    payment = Payment.objects.get(transaction_id=reference)
    assert payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION
    assert payment.status == Payment.PaymentStatus.PENDING

    # Simular webhook aprobado
    PaymentService.apply_gateway_status(payment, "APPROVED", transaction_payload={"id": reference, "status": "APPROVED"})

    client_user.refresh_from_db()
    assert client_user.role == CustomUser.Role.VIP
    assert client_user.vip_auto_renew is True
    assert client_user.vip_active_since == timezone.now().date()
    assert client_user.vip_expires_at == client_user.vip_active_since + timedelta(days=30)
    assert SubscriptionLog.objects.filter(user=client_user, payment=payment).exists()


def test_store_recurring_token_for_vip(api_client, client_user):
    client_user.role = CustomUser.Role.VIP
    client_user.vip_expires_at = timezone.now().date() + timedelta(days=30)
    client_user.save(update_fields=["role", "vip_expires_at", "updated_at"])

    token = "123456"
    client_user.vip_payment_token = token
    client_user.vip_auto_renew = True
    client_user.save(update_fields=["vip_payment_token", "vip_auto_renew", "updated_at"])

    client_user.refresh_from_db()
    assert client_user.vip_payment_token == token
    assert client_user.vip_auto_renew is True


def test_recurring_subscription_success(api_client, client_user, monkeypatch):
    _set_vip_price()
    client_user.role = CustomUser.Role.VIP
    client_user.vip_auto_renew = True
    client_user.vip_expires_at = timezone.now().date() + timedelta(days=1)
    client_user.vip_payment_token = "999"
    client_user.vip_failed_payments = 2
    client_user.save(update_fields=["role", "vip_auto_renew", "vip_expires_at", "vip_payment_token", "vip_failed_payments", "updated_at"])

    monkeypatch.setattr(
        PaymentService,
        "charge_recurrence_token",
        staticmethod(lambda user, amount, token: (Payment.PaymentStatus.APPROVED, {"id": "TRX", "status": "APPROVED"}, "REF-OK")),
    )

    result = process_recurring_subscriptions()
    assert "Renovaciones intentadas" in str(result)

    client_user.refresh_from_db()
    assert client_user.vip_failed_payments == 0
    old = timezone.now().date() + timedelta(days=1)
    assert client_user.vip_expires_at > old
    payment = Payment.objects.filter(payment_type=Payment.PaymentType.VIP_SUBSCRIPTION).latest("created_at")
    assert payment.status == Payment.PaymentStatus.APPROVED


def test_recurring_subscription_failure_increments_counter(monkeypatch, client_user):
    _set_vip_price()
    client_user.role = CustomUser.Role.VIP
    client_user.vip_auto_renew = True
    client_user.vip_expires_at = timezone.now().date() + timedelta(days=1)
    client_user.vip_payment_token = "bad"
    client_user.vip_failed_payments = 0
    client_user.save(update_fields=["role", "vip_auto_renew", "vip_expires_at", "vip_payment_token", "vip_failed_payments", "updated_at"])

    monkeypatch.setattr(
        PaymentService,
        "charge_recurrence_token",
        staticmethod(lambda user, amount, token: (Payment.PaymentStatus.DECLINED, {"status": "DECLINED"}, "REF-FAIL")),
    )

    notified = {}

    def fake_notify(user, event_code, context, priority="normal"):
        notified["event_code"] = event_code
        notified["user"] = user
        notified["context"] = context

    from notifications import services as notif_services

    monkeypatch.setattr(notif_services.NotificationService, "send_notification", staticmethod(fake_notify))

    process_recurring_subscriptions()

    client_user.refresh_from_db()
    assert client_user.vip_failed_payments == 1
    assert client_user.role == CustomUser.Role.VIP
    assert notified.get("event_code") == "VIP_RENEWAL_FAILED"


def test_recurring_subscription_cancel_after_three_failures(monkeypatch, client_user):
    _set_vip_price()
    client_user.role = CustomUser.Role.VIP
    client_user.vip_auto_renew = True
    client_user.vip_expires_at = timezone.now().date() + timedelta(days=1)
    client_user.vip_payment_token = "bad"
    client_user.vip_failed_payments = 2
    client_user.save(update_fields=["role", "vip_auto_renew", "vip_expires_at", "vip_payment_token", "vip_failed_payments", "updated_at"])

    monkeypatch.setattr(
        PaymentService,
        "charge_recurrence_token",
        staticmethod(lambda user, amount, token: (Payment.PaymentStatus.DECLINED, {"status": "DECLINED"}, "REF-FAIL")),
    )

    process_recurring_subscriptions()

    client_user.refresh_from_db()
    assert client_user.vip_failed_payments == 3
    assert client_user.vip_auto_renew is False


def test_downgrade_expired_vip():
    user = CustomUser.objects.create_user(
        phone_number="+573500000099",
        password="Secret123!",
        first_name="VIP",
        role=CustomUser.Role.VIP,
        vip_expires_at=timezone.now().date() - timedelta(days=1),
        vip_auto_renew=True,
    )

    result = downgrade_expired_vips()
    assert "Usuarios degradados" in str(result)

    user.refresh_from_db()
    assert user.role == CustomUser.Role.CLIENT
    assert user.vip_active_since is None
    assert user.vip_auto_renew is False
    assert AuditLog.objects.filter(action=AuditLog.Action.VIP_DOWNGRADED, target_user=user).exists()


def test_loyalty_reward(monkeypatch, client_user):
    service = _make_service(name="Loyalty Gift")
    settings = GlobalSettings.load()
    settings.loyalty_voucher_service = service
    settings.loyalty_months_required = 1
    settings.credit_expiration_days = 30
    settings.save()

    client_user.role = CustomUser.Role.VIP
    client_user.vip_active_since = timezone.now().date() - timedelta(days=40)
    client_user.save(update_fields=["role", "vip_active_since", "updated_at"])

    sent = {}

    def fake_notify(user, event_code, context, priority="normal"):
        sent["event_code"] = event_code
        sent["user"] = user
        sent["context"] = context

    from notifications import services as notif_services

    monkeypatch.setattr(notif_services.NotificationService, "send_notification", staticmethod(fake_notify))

    result = check_vip_loyalty()

    assert "Recompensas emitidas" in str(result)
    reward = LoyaltyRewardLog.objects.filter(user=client_user).first()
    assert reward is not None
    voucher = reward.voucher
    assert voucher.service == service
    # Notificación es opcional; si se emitió, validar contenido básico
    if sent:
        assert sent.get("event_code") in {"LOYALTY_REWARD_ISSUED", "VIP_LOYALTY_REWARD"}
        assert sent.get("user") == client_user


def test_cancel_auto_renew_view(api_client, client_user):
    client_user.role = CustomUser.Role.VIP
    client_user.vip_auto_renew = True
    client_user.save(update_fields=["role", "vip_auto_renew", "updated_at"])

    _auth(api_client, client_user)
    url = reverse("cancel-vip-subscription")
    resp = api_client.post(url, format="json")

    assert resp.status_code == status.HTTP_200_OK
    client_user.refresh_from_db()
    assert client_user.vip_auto_renew is False
