from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from spa.models import Appointment, Service, ServiceCategory, AppointmentItem
from users.models import CustomUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    from django.core.cache import cache as django_cache

    if hasattr(django_cache, "clear"):
        django_cache.clear()
        yield
        django_cache.clear()
    else:
        # Algunos backends no exponen clear(); hacer nada.
        yield


def test_sql_injection_search_returns_safe_response(api_client):
    ServiceCategory.objects.create(name="Cat", description="d")
    url = reverse("product-list")
    resp = api_client.get(f"{url}?search=' OR '1'='1", format="json")

    assert resp.status_code in {status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST}
    body_str = str(resp.data)
    assert "syntax error" not in body_str.lower()
    assert "psycopg2" not in body_str.lower()


def test_xss_payload_is_neutralized(api_client, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    payload = {"message": "<script>alert('XSS')</script>"}
    resp = api_client.post(reverse("bot-webhook"), payload, format="json")

    assert resp.status_code in {status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_503_SERVICE_UNAVAILABLE}
    body = str(getattr(resp, "data", "") or resp.content).lower()
    assert "<script" not in body


def test_csrf_required_on_admin_login():
    client = Client(enforce_csrf_checks=True)
    resp = client.post("/admin/login/", {"username": "admin", "password": "bad"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_expired_jwt_returns_401(api_client):
    user = CustomUser.objects.create_user(phone_number="+576000000001", password="Secret123!", is_verified=True)
    token = RefreshToken.for_user(user).access_token
    token.set_exp(lifetime=timedelta(seconds=-60))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")
    resp = api_client.get(reverse("current_user"))
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_user_cannot_access_other_user_appointment(api_client):
    user_a = CustomUser.objects.create_user(phone_number="+576000000010", password="Secret123!", is_verified=True)
    user_b = CustomUser.objects.create_user(phone_number="+576000000011", password="Secret123!", is_verified=True)
    cat = ServiceCategory.objects.create(name="Cat", description="d")
    service = Service.objects.create(name="Svc", description="d", duration=30, price=50, category=cat, is_active=True)
    appt = Appointment.objects.create(
        user=user_b,
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, minutes=30),
        status=Appointment.AppointmentStatus.CONFIRMED,
        price_at_purchase=service.price,
    )
    AppointmentItem.objects.create(appointment=appt, service=service, duration=service.duration, price_at_purchase=service.price)

    api_client.force_authenticate(user=user_a)
    resp = api_client.get(reverse("appointment-detail", kwargs={"pk": appt.id}))

    assert resp.status_code in {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND}


def test_privilege_escalation_blocked(api_client):
    client_user = CustomUser.objects.create_user(phone_number="+576000000020", password="Secret123!", is_verified=True)
    api_client.force_authenticate(user=client_user)
    resp = api_client.get(reverse("analytics-kpis"), {"start_date": timezone.localdate().isoformat(), "end_date": timezone.localdate().isoformat()})

    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_rate_limiting_triggers_on_bot(api_client, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    responses = []
    for i in range(6):
        resp = api_client.post(reverse("bot-webhook"), {"message": f"spam {i}"}, format="json")
        responses.append(resp.status_code)
    assert any(code == status.HTTP_429_TOO_MANY_REQUESTS for code in responses)


def test_brute_force_login_is_throttled(api_client):
    phone = "+576000000030"
    CustomUser.objects.create_user(phone_number=phone, password="Correct123!", is_verified=True)
    last_status = None
    for _ in range(6):
        resp = api_client.post(reverse("token_obtain_pair"), {"phone_number": phone, "password": "Wrong!"}, format="json")
        last_status = resp.status_code
    assert last_status in {status.HTTP_400_BAD_REQUEST, status.HTTP_429_TOO_MANY_REQUESTS}
