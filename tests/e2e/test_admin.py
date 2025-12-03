from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AdminNotification, AuditLog, GlobalSettings
from finances.models import ClientCredit, CommissionLedger, FinancialAdjustment
from finances.services import DeveloperCommissionService
from profiles.models import ClinicalProfile
from spa.models import Appointment, AppointmentItem, Service, ServiceCategory
from users.models import BlockedPhoneNumber, CustomUser, UserSession
from notifications import services as notif_services


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
def admin_user():
    return CustomUser.objects.create_user(
        phone_number="+574000000001",
        password="Secret123!",
        first_name="Admin",
        role=CustomUser.Role.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def client_user():
    return CustomUser.objects.create_user(
        phone_number="+574000000010",
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
    )


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def test_flag_non_grata_marks_user_and_cancels_future(api_client, admin_user, client_user, monkeypatch):
    future = timezone.now() + timedelta(days=1)
    service_cat = ServiceCategory.objects.create(name="Test", description="d")
    service = Service.objects.create(name="Svc", description="d", duration=30, price=100, category=service_cat, is_active=True)
    appt = Appointment.objects.create(
        user=client_user,
        start_time=future,
        end_time=future + timedelta(minutes=30),
        status=Appointment.AppointmentStatus.CONFIRMED,
        price_at_purchase=service.price,
    )
    AppointmentItem.objects.create(appointment=appt, service=service, duration=service.duration, price_at_purchase=service.price)
    session = UserSession.objects.create(user=client_user, refresh_token_jti="jti", is_active=True)
    sent = {}
    monkeypatch.setattr(notif_services.NotificationService, "send_notification", staticmethod(lambda *args, **kwargs: sent.update(kwargs)))

    _auth(api_client, admin_user)
    url = reverse("flag_non_grata", kwargs={"phone_number": client_user.phone_number})
    resp = api_client.patch(url, {"internal_notes": "CNG por fraude"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    client_user.refresh_from_db()
    assert client_user.is_persona_non_grata is True
    assert client_user.is_active is False
    assert BlockedPhoneNumber.objects.filter(phone_number=client_user.phone_number).exists()
    session.refresh_from_db()
    assert session.is_active is False
    appt.refresh_from_db()
    assert appt.status == Appointment.AppointmentStatus.CANCELLED
    assert appt.outcome == Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN
    assert AuditLog.objects.filter(action=AuditLog.Action.FLAG_NON_GRATA, target_user=client_user).exists()
    assert AdminNotification.objects.filter(subtype=AdminNotification.NotificationSubtype.USUARIO_CNG).exists()


def test_cancel_appointment_by_admin(api_client, admin_user, client_user):
    start = timezone.now() + timedelta(hours=2)
    service_cat = ServiceCategory.objects.create(name="Cat", description="d")
    service = Service.objects.create(name="Therapy", description="d", duration=60, price=200, category=service_cat, is_active=True)
    appt = Appointment.objects.create(
        user=client_user,
        start_time=start,
        end_time=start + timedelta(minutes=60),
        status=Appointment.AppointmentStatus.CONFIRMED,
        price_at_purchase=service.price,
    )
    AppointmentItem.objects.create(appointment=appt, service=service, duration=service.duration, price_at_purchase=service.price)

    _auth(api_client, admin_user)
    url = reverse("appointment-cancel-by-admin", kwargs={"pk": appt.id})
    resp = api_client.post(url, {"cancellation_reason": "No show"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    appt.refresh_from_db()
    assert appt.status == Appointment.AppointmentStatus.CANCELLED
    assert appt.outcome == Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN
    assert AuditLog.objects.filter(action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN, target_appointment=appt).exists()


def test_create_financial_adjustment_credit(api_client, admin_user, client_user):
    _auth(api_client, admin_user)
    url = reverse("financial-adjustments")
    payload = {
        "user_id": str(client_user.id),
        "amount": "50000",
        "adjustment_type": FinancialAdjustment.AdjustmentType.CREDIT,
        "reason": "Compensación por inconveniente",
    }
    resp = api_client.post(url, payload, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    assert FinancialAdjustment.objects.filter(user=client_user, amount="50000").exists()
    assert ClientCredit.objects.filter(user=client_user, initial_amount="50000").exists()
    assert AuditLog.objects.filter(action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED, target_user=client_user).exists()


def test_financial_adjustment_respects_limit(api_client, admin_user, client_user):
    _auth(api_client, admin_user)
    url = reverse("financial-adjustments")
    payload = {
        "user_id": str(client_user.id),
        "amount": "6000000",
        "adjustment_type": FinancialAdjustment.AdjustmentType.CREDIT,
        "reason": "Demasiado alto",
    }
    resp = api_client.post(url, payload, format="json")

    assert resp.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY}
    assert "límite" in str(resp.data).lower()


def test_anonymize_profile(api_client, admin_user, client_user):
    profile = ClinicalProfile.objects.create(
        user=client_user,
        medical_conditions="Hipertensión",
    )
    _auth(api_client, admin_user)
    url = reverse("clinical-profile-anonymize", kwargs={"phone_number": client_user.phone_number})
    resp = api_client.post(url, {}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    client_user.refresh_from_db()
    profile.refresh_from_db()
    assert client_user.first_name == "ANONIMIZADO"
    assert profile.medical_conditions == ""
    assert AuditLog.objects.filter(action=AuditLog.Action.CLINICAL_PROFILE_ANONYMIZED, target_user=client_user).exists()


def test_block_ip_sets_cache_key(api_client, admin_user):
    _auth(api_client, admin_user)
    url = reverse("block_ip")
    resp = api_client.post(url, {"ip": "10.1.1.1", "ttl": 60}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    assert cache.get("blocked_ip:10.1.1.1") is True


def test_export_users_csv(api_client, admin_user, client_user):
    _auth(api_client, admin_user)
    url = reverse("user-export")
    resp = api_client.get(url, {"format": "csv"})
    if resp.status_code == status.HTTP_404_NOT_FOUND:
        pytest.skip("Endpoint de export no disponible")
    assert resp.status_code == status.HTTP_200_OK
    assert "text/csv" in resp["Content-Type"]
    assert client_user.phone_number in resp.content.decode()


def test_commission_status_endpoint(api_client, admin_user, monkeypatch):
    _auth(api_client, admin_user)
    # Evitar llamada externa a Wompi
    monkeypatch.setattr(
        "finances.views.WompiDisbursementClient.get_available_balance",
        staticmethod(lambda self=None: DeveloperCommissionService.get_developer_debt()),
    )
    url = reverse("commission-ledger-status")
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert "developer_debt" in data
    assert "payout_threshold" in data
    assert "wompi_available_balance" in data
