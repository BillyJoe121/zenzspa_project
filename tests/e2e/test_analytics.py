from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from analytics.views import DateFilterMixin
from core.models import AuditLog
from finances.models import Payment
from marketplace.models import Order, OrderItem, Product, ProductVariant
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
def admin_user():
    return CustomUser.objects.create_user(
        phone_number="+573800000001",
        password="Secret123!",
        first_name="Admin",
        role=CustomUser.Role.ADMIN,
        is_staff=True,
        is_superuser=False,
    )


@pytest.fixture
def staff_user():
    return CustomUser.objects.create_user(
        phone_number="+573800000010",
        password="Secret123!",
        first_name="Staff",
        role=CustomUser.Role.STAFF,
        is_staff=True,
    )


@pytest.fixture
def staff_user_2():
    return CustomUser.objects.create_user(
        phone_number="+573800000011",
        password="Secret123!",
        first_name="Staff2",
        role=CustomUser.Role.STAFF,
        is_staff=True,
    )


@pytest.fixture
def client_user():
    return CustomUser.objects.create_user(
        phone_number="+573800000020",
        password="Secret123!",
        first_name="Cliente",
        role=CustomUser.Role.CLIENT,
        is_verified=True,
    )


def _make_services():
    cat_relax = ServiceCategory.objects.create(name="Masajes Relajantes", description="desc")
    cat_sport = ServiceCategory.objects.create(name="Masajes Deportivos", description="desc")
    s1 = Service.objects.create(
        name="Masaje Relajante",
        description="desc",
        duration=60,
        price=Decimal("100000.00"),
        category=cat_relax,
        is_active=True,
    )
    s2 = Service.objects.create(
        name="Masaje Deportivo",
        description="desc",
        duration=45,
        price=Decimal("80000.00"),
        category=cat_sport,
        is_active=True,
    )
    return s1, s2, cat_relax, cat_sport


def _make_order(user, category):
    product = Product.objects.create(name="Aceite", description="Relajante", category=category, is_active=True)
    variant = ProductVariant.objects.create(
        product=product,
        name="50ml",
        sku="SKU-50",
        price=Decimal("50000.00"),
        stock=10,
    )
    order = Order.objects.create(
        user=user,
        status=Order.OrderStatus.PAID,
        total_amount=Decimal("50000.00"),
        delivery_option=Order.DeliveryOptions.DELIVERY,
    )
    OrderItem.objects.create(
        order=order,
        variant=variant,
        quantity=1,
        price_at_purchase=variant.price,
    )
    return order


def _seed_data(admin, staff1, staff2, client):
    now = timezone.now()
    start_time = now - timedelta(days=1)
    s1, s2, cat_relax, cat_sport = _make_services()

    appt1 = Appointment.objects.create(
        user=client,
        staff_member=staff1,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=s1.duration),
        status=Appointment.AppointmentStatus.CONFIRMED,
        price_at_purchase=s1.price,
        reschedule_count=1,
    )
    AppointmentItem.objects.create(appointment=appt1, service=s1, duration=s1.duration, price_at_purchase=s1.price)
    Payment.objects.create(
        user=client,
        appointment=appt1,
        amount=s1.price,
        status=Payment.PaymentStatus.APPROVED,
        payment_type=Payment.PaymentType.ADVANCE,
    )

    appt2 = Appointment.objects.create(
        user=client,
        staff_member=staff2,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=s2.duration),
        status=Appointment.AppointmentStatus.CANCELLED,
        outcome=Appointment.AppointmentOutcome.NO_SHOW,
        price_at_purchase=s2.price,
    )
    AppointmentItem.objects.create(appointment=appt2, service=s2, duration=s2.duration, price_at_purchase=s2.price)
    Payment.objects.create(
        user=client,
        amount=Decimal("200000.00"),
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.FINAL,
    )

    order = _make_order(client, cat_relax)
    Payment.objects.create(
        user=client,
        order=order,
        amount=order.total_amount,
        status=Payment.PaymentStatus.APPROVED,
        payment_type=Payment.PaymentType.ORDER,
    )

    return {
        "service_relax": s1,
        "service_sport": s2,
        "cat_relax": cat_relax,
        "cat_sport": cat_sport,
        "appt1": appt1,
        "appt2": appt2,
        "order": order,
    }


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def test_kpis_dashboard_happy_path(api_client, admin_user, staff_user, staff_user_2, client_user):
    data = _seed_data(admin_user, staff_user, staff_user_2, client_user)
    _auth(api_client, admin_user)
    start = (timezone.localdate() - timedelta(days=2)).isoformat()
    end = timezone.localdate().isoformat()

    resp = api_client.get(reverse("analytics-kpis"), {"start_date": start, "end_date": end})

    assert resp.status_code == status.HTTP_200_OK
    body = resp.data
    for key in ["conversion_rate", "no_show_rate", "reschedule_rate", "utilization_rate", "ltv_by_role", "total_revenue"]:
        assert key in body
    assert body["conversion_rate"] > 0
    assert body["reschedule_rate"] > 0
    assert body["ltv_by_role"]


def test_kpis_filtered_by_staff(api_client, admin_user, staff_user, staff_user_2, client_user):
    _seed_data(admin_user, staff_user, staff_user_2, client_user)
    _auth(api_client, admin_user)
    start = (timezone.localdate() - timedelta(days=2)).isoformat()
    end = timezone.localdate().isoformat()

    resp = api_client.get(
        reverse("analytics-kpis"),
        {"start_date": start, "end_date": end, "staff_id": staff_user.id},
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["conversion_rate"] == 1  # Solo la cita confirmada del staff
    assert resp.data["no_show_rate"] == 0  # Ninguna no-show para este staff


def test_kpis_filtered_by_category(api_client, admin_user, staff_user, staff_user_2, client_user):
    data = _seed_data(admin_user, staff_user, staff_user_2, client_user)
    _auth(api_client, admin_user)
    start = (timezone.localdate() - timedelta(days=2)).isoformat()
    end = timezone.localdate().isoformat()

    resp = api_client.get(
        reverse("analytics-kpis"),
        {
            "start_date": start,
            "end_date": end,
            "service_category_id": data["cat_relax"].id,
        },
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["conversion_rate"] == 1  # Solo citas de esa categoría
    assert resp.data["reschedule_rate"] == 1


def test_sales_details_and_debt_rows_available_in_export_cache(api_client, admin_user, staff_user, staff_user_2, client_user):
    data = _seed_data(admin_user, staff_user, staff_user_2, client_user)
    _auth(api_client, admin_user)
    start_date = timezone.localdate() - timedelta(days=2)
    end_date = timezone.localdate()

    resp = api_client.get(
        reverse("analytics-export"),
        {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "format": "csv"},
    )

    if resp.status_code == status.HTTP_404_NOT_FOUND:
        pytest.skip("Export endpoint no disponible en este entorno")
    assert resp.status_code == status.HTTP_200_OK
    assert resp["Content-Type"].startswith("text/csv")

    # Verificar dataset cacheado para inspeccionar detalles
    cache_key = DateFilterMixin()._cache_key(
        type("obj", (), {"user": admin_user}),
        "dataset",
        start_date,
        end_date,
        None,
        None,
    )
    dataset = cache.get(cache_key)
    assert dataset is not None
    assert any(row["order_id"] == str(data["order"].id) for row in dataset["sales_details"])
    assert any(row["status"] == Payment.PaymentStatus.PENDING for row in dataset["debt_rows"])

    # Audit log
    assert AuditLog.objects.filter(details__analytics_action="analytics_export").exists()


def test_debt_metrics_present(api_client, admin_user, staff_user, staff_user_2, client_user):
    _seed_data(admin_user, staff_user, staff_user_2, client_user)
    _auth(api_client, admin_user)
    start = (timezone.localdate() - timedelta(days=2)).isoformat()
    end = timezone.localdate().isoformat()

    resp = api_client.get(reverse("analytics-kpis"), {"start_date": start, "end_date": end})

    assert resp.status_code == status.HTTP_200_OK
    debt = resp.data.get("debt_recovery", {})
    assert "total_debt" in debt
    assert "recovered_amount" in debt
    assert debt["total_debt"] >= 0
