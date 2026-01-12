from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from spa.models import (
    Appointment,
    AppointmentItem,
    Service,
    ServiceCategory,
    StaffAvailability,
    WaitlistEntry,
)
from core.models import GlobalSettings
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
    user = CustomUser.objects.create_user(
        phone_number="+573300000001",
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
    )
    return user


@pytest.fixture
def staff_user():
    user = CustomUser.objects.create_user(
        phone_number="+573300000099",
        password="Staff123!",
        first_name="Staff",
        last_name="Ejemplo",
        role=CustomUser.Role.STAFF,
        is_staff=True,
        is_verified=True,
    )
    # El signal crea horarios por defecto; los limpiamos para evitar solapamientos en pruebas controladas.
    StaffAvailability.objects.filter(staff_member=user).delete()
    return user


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def _make_service(name="Masaje Relajante", duration=60, price=Decimal("100000")):
    category = ServiceCategory.objects.create(name=f"Cat {name}", description="desc")
    return Service.objects.create(
        name=name,
        description="Relax",
        duration=duration,
        price=price,
        category=category,
        is_active=True,
    )


def _schedule_time(days=1, hour=10, minute=0):
    tz = timezone.get_current_timezone()
    base = timezone.now().astimezone(tz) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _add_staff_availability(staff, start_time, end_time):
    StaffAvailability.objects.create(
        staff_member=staff,
        day_of_week=start_time.isoweekday(),
        start_time=start_time.time(),
        end_time=end_time.time(),
    )


def test_service_catalog_lists_only_active(api_client):
    active = _make_service(name="Activo", price=Decimal("50000"))
    inactive_cat = ServiceCategory.objects.create(name="Cat Inactivo", description="x")
    Service.objects.create(
        name="Inactivo",
        description="desc",
        duration=30,
        price=Decimal("20000"),
        category=inactive_cat,
        is_active=False,
    )

    url = reverse("service-list")
    resp = api_client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    names = [s["name"] for s in data]
    assert "Activo" in names
    assert "Inactivo" not in names


def test_availability_happy_path(api_client, client_user, staff_user):
    service = _make_service()
    start = _schedule_time(days=2, hour=10)
    end = start + timedelta(hours=2)
    _add_staff_availability(staff_user, start, end)

    _auth(api_client, client_user)
    url = reverse("availability-check")
    resp = api_client.get(
        url,
        {"service_ids": [str(service.id)], "date": str(start.date())},
    )

    assert resp.status_code == status.HTTP_200_OK
    slots = resp.data
    assert any(slot["staff_name"] for slot in slots)
    assert any(slot["start_time"].startswith(start.replace(minute=0).isoformat()[:16]) for slot in slots)


def test_availability_no_slots(api_client, client_user, staff_user):
    service = _make_service()
    start = _schedule_time(days=2, hour=10)
    end = start + timedelta(minutes=30)
    # Staff availability but already fully blocked by existing appointment with buffer
    _add_staff_availability(staff_user, start, end + timedelta(minutes=15))

    # Create blocking appointment
    Appointment.objects.create(
        user=client_user,
        staff_member=staff_user,
        start_time=start,
        end_time=end,
        price_at_purchase=service.price,
        status=Appointment.AppointmentStatus.CONFIRMED,
    )

    _auth(api_client, client_user)
    url = reverse("availability-check")
    resp = api_client.get(
        url,
        {"service_ids": [str(service.id)], "date": str(start.date())},
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == []


def test_create_appointment_happy_path(api_client, client_user, staff_user):
    service = _make_service(price=Decimal("80000"))
    start = _schedule_time(days=3, hour=9)
    end = start + timedelta(hours=2)
    _add_staff_availability(staff_user, start, end)

    _auth(api_client, client_user)
    url = reverse("appointment-list")
    resp = api_client.post(
        url,
        {
            "service_ids": [str(service.id)],
            "staff_member": str(staff_user.id),
            "start_time": start.replace(minute=0).isoformat(),
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    appt = Appointment.objects.get(id=resp.data["id"])
    assert appt.status == Appointment.AppointmentStatus.PENDING_PAYMENT
    assert appt.price_at_purchase == service.price
    assert appt.items.count() == 1


def test_create_appointment_conflict(api_client, client_user, staff_user):
    service = _make_service()
    start = _schedule_time(days=2, hour=11)
    end = start + timedelta(hours=2)
    _add_staff_availability(staff_user, start, end)

    Appointment.objects.create(
        user=client_user,
        staff_member=staff_user,
        start_time=start,
        end_time=start + timedelta(minutes=service.duration),
        price_at_purchase=service.price,
        status=Appointment.AppointmentStatus.CONFIRMED,
    )

    _auth(api_client, client_user)
    url = reverse("appointment-list")
    resp = api_client.post(
        url,
        {
            "service_ids": [str(service.id)],
            "staff_member": str(staff_user.id),
            "start_time": start.isoformat(),
        },
        format="json",
    )

    assert resp.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT)
    assert "no está disponible" in str(resp.data).lower()


def test_reschedule_within_policy(api_client, client_user, staff_user):
    service = _make_service()
    start = _schedule_time(days=3, hour=14)
    end = start + timedelta(minutes=service.duration)
    new_start = start + timedelta(days=2)
    _add_staff_availability(staff_user, start, start + timedelta(hours=4))
    _add_staff_availability(staff_user, new_start, new_start + timedelta(hours=2))

    appt = Appointment.objects.create(
        user=client_user,
        staff_member=staff_user,
        start_time=start,
        end_time=end,
        price_at_purchase=service.price,
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    AppointmentItem.objects.create(appointment=appt, service=service, duration=service.duration, price_at_purchase=service.price)

    _auth(api_client, client_user)
    url = reverse("appointment-reschedule", kwargs={"pk": appt.id})
    resp = api_client.post(url, {"new_start_time": new_start.isoformat()}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    appt.refresh_from_db()
    assert appt.status == Appointment.AppointmentStatus.RESCHEDULED
    assert appt.reschedule_count == 1
    assert appt.start_time == new_start


def test_reschedule_under_24h_denied_for_client(api_client, client_user, staff_user):
    service = _make_service()
    tz = timezone.get_current_timezone()
    start = (timezone.now().astimezone(tz) + timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=service.duration)
    new_start = start + timedelta(hours=2)  # libre respecto a buffer
    _add_staff_availability(staff_user, start, start + timedelta(hours=4))

    appt = Appointment.objects.create(
        user=client_user,
        staff_member=staff_user,
        start_time=start,
        end_time=end,
        price_at_purchase=service.price,
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    AppointmentItem.objects.create(appointment=appt, service=service, duration=service.duration, price_at_purchase=service.price)

    _auth(api_client, client_user)
    url = reverse("appointment-reschedule", kwargs={"pk": appt.id})
    resp = api_client.post(url, {"new_start_time": new_start.isoformat()}, format="json")

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "24 horas" in str(resp.data.get("error", "")).lower()


def test_waitlist_join(api_client, client_user):
    settings = GlobalSettings.load()
    settings.waitlist_enabled = True
    settings.save()
    service = _make_service()

    _auth(api_client, client_user)
    url = reverse("appointment-waitlist-join")
    desired = (timezone.now() + timedelta(days=2)).date()
    resp = api_client.post(
        url,
        {"desired_date": desired, "service_ids": [str(service.id)], "notes": "Prefiero mañana"},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    entry = WaitlistEntry.objects.get(id=resp.data["id"])
    assert entry.status == WaitlistEntry.Status.WAITING
    assert entry.desired_date == desired
    assert entry.services.filter(id=service.id).exists()
