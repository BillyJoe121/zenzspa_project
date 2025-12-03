import time
from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from analytics.services import KpiService
from finances.webhooks import WompiWebhookService
from spa.models import Appointment, AppointmentItem, Service, ServiceCategory
from users.models import CustomUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def test_service_catalog_response_time(api_client, settings):
    # Sembrar 100 servicios
    category = ServiceCategory.objects.create(name="PerfCat", description="d")
    for i in range(100):
        Service.objects.create(
            name=f"Svc {i}",
            description="desc",
            duration=60,
            price=Decimal("50000.00"),
            category=category,
            is_active=True,
        )
    url = reverse("service-list")
    start = time.perf_counter()
    resp = api_client.get(url, {"page": 1}, format="json")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == status.HTTP_200_OK
    assert elapsed_ms < 500
    assert "results" in resp.data


def test_concurrent_appointment_creation(api_client):
    category = ServiceCategory.objects.create(name="PerfSlot", description="d")
    service = Service.objects.create(
        name="Masaje Perf",
        description="desc",
        duration=60,
        price=Decimal("80000.00"),
        category=category,
        is_active=True,
    )
    staff = CustomUser.objects.create_user(
        phone_number="+577000000050",
        password="Secret123!",
        first_name="Staff",
        role=CustomUser.Role.STAFF,
        is_staff=True,
    )
    # Mismo slot
    start_time = timezone.now() + timedelta(hours=2)
    end_time = start_time + timedelta(minutes=60)
    payload = {
        "services": [service.id],
        "staff_member": staff.id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }

    users = [
        CustomUser.objects.create_user(
            phone_number=f"+5770000001{i}",
            password="Secret123!",
            first_name=f"User{i}",
            is_verified=True,
        )
        for i in range(10)
    ]

    def attempt(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.post(reverse("appointment-list"), payload, format="json").status_code

    successes = 0
    conflicts = 0
    others = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt, u) for u in users]
        for fut in as_completed(futures):
            code = fut.result()
            if code == status.HTTP_201_CREATED:
                successes += 1
            elif code in {status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, status.HTTP_403_FORBIDDEN}:
                conflicts += 1
            else:
                others += 1

    assert successes <= 1
    assert conflicts + successes + others == len(users)
    assert conflicts >= 8  # al menos la mayoría debe fallar por conflicto/validación


def test_webhook_under_load(api_client, settings):
    settings.WOMPI_EVENT_SECRET = "secret"
    payload_template = {
        "event": "transaction.updated",
        "data": {"transaction": {"id": "wompi-id", "amount_in_cents": 5000000, "status": "APPROVED", "reference": "ref"}},
        "signature": {
            "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents", "transaction.reference"],
            "checksum": "",
        },
        "timestamp": int(timezone.now().timestamp()),
    }

    def sign(ref):
        payload = dict(payload_template)
        payload["data"] = {"transaction": dict(payload_template["data"]["transaction"], reference=ref)}
        payload["timestamp"] = int(timezone.now().timestamp())
        properties = payload["signature"]["properties"]
        values = []
        data = payload["data"]
        for prop_path in properties:
            keys = prop_path.split(".")
            value = data
            for key in keys:
                value = value.get(key, "") if isinstance(value, dict) else ""
            values.append(str(value))
        concatenated = "".join(values) + str(payload["timestamp"]) + settings.WOMPI_EVENT_SECRET
        import hashlib

        payload["signature"]["checksum"] = hashlib.sha256(concatenated.encode("utf-8")).hexdigest().upper()
        return payload

    refs = [f"ref-{i}" for i in range(100)]
    start = time.perf_counter()
    statuses = []
    for ref in refs:
        resp = api_client.post(reverse("wompi-webhook"), sign(ref), format="json")
        statuses.append(resp.status_code)
    elapsed = time.perf_counter() - start

    acceptable = {status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND, status.HTTP_429_TOO_MANY_REQUESTS}
    assert all(code in acceptable for code in statuses)
    assert elapsed <= 10


def test_analytics_kpis_cached(api_client, settings):
    admin = CustomUser.objects.create_user(
        phone_number="+577000000999",
        password="Secret123!",
        role=CustomUser.Role.ADMIN,
        is_staff=True,
    )
    api_client.force_authenticate(user=admin)
    today = timezone.localdate()
    start_date = (today - timedelta(days=30)).isoformat()
    end_date = today.isoformat()

    # Primera llamada
    t0 = time.perf_counter()
    resp1 = api_client.get(reverse("analytics-kpis"), {"start_date": start_date, "end_date": end_date})
    t1 = (time.perf_counter() - t0)

    # Segunda llamada (esperamos cache)
    t2 = time.perf_counter()
    resp2 = api_client.get(reverse("analytics-kpis"), {"start_date": start_date, "end_date": end_date})
    t3 = (time.perf_counter() - t2)

    assert resp1.status_code == status.HTTP_200_OK
    assert resp2.status_code == status.HTTP_200_OK
    assert t1 < 5  # segundos
    assert t3 <= t1  # segunda debe ser igual o más rápida por cache
