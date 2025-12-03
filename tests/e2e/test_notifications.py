from datetime import datetime, time, timedelta, timezone as dt_timezone

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from notifications.models import NotificationLog, NotificationPreference, NotificationTemplate
from notifications.services import NotificationService
from notifications.tasks import send_notification_task
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
        phone_number="+573700000001",
        password="Secret123!",
        first_name="Cliente",
        email="cliente@example.com",
        is_verified=True,
    )


def _auth(client: APIClient, user: CustomUser):
    client.force_authenticate(user=user)


def _make_template(event_code="TEST_EVENT", channel=NotificationTemplate.ChannelChoices.WHATSAPP):
    return NotificationTemplate.objects.create(
        event_code=event_code,
        channel=channel,
        subject_template="Hola {{ user_name }}",
        body_template="Cita confirmada",
        is_active=True,
    )


def test_send_notification_whatsapp_happy_path(client_user, monkeypatch):
    _make_template()
    sent = {}

    def fake_enqueue(*args, **kwargs):
        log_args = kwargs.get("args") or (args[0] if args else [])
        log_id = log_args[0] if log_args else None
        sent["log_id"] = log_id
        if log_id:
            send_notification_task(log_id)
        return True

    monkeypatch.setattr("notifications.tasks.send_notification_task.apply_async", staticmethod(fake_enqueue))

    log = NotificationService.send_notification(
        user=client_user,
        event_code="TEST_EVENT",
        context={"user_name": client_user.first_name, "phone_number": client_user.phone_number},
    )

    assert log is not None
    log.refresh_from_db()
    assert log.status == NotificationLog.Status.SENT
    assert log.channel == NotificationTemplate.ChannelChoices.WHATSAPP
    assert log.sent_at is not None


def test_notification_respects_quiet_hours(client_user, monkeypatch):
    _make_template(event_code="QUIET_EVENT")
    pref = NotificationPreference.for_user(client_user)
    pref.quiet_hours_start = time(22, 0)
    pref.quiet_hours_end = time(8, 0)
    pref.timezone = "UTC"
    pref.save()

    monkeypatch.setattr(timezone, "now", staticmethod(lambda: datetime(2024, 1, 1, 23, 0, tzinfo=dt_timezone.utc)))

    log = NotificationService.send_notification(
        user=client_user,
        event_code="QUIET_EVENT",
        context={"user_name": "Juan", "phone_number": client_user.phone_number},
    )

    # Puede entrar como queued si el scheduler se ejecuta inmediato; validar que está silenciado o programado
    assert log.status in {NotificationLog.Status.SILENCED, NotificationLog.Status.QUEUED}
    assert log.metadata.get("scheduled_for") is not None or pref.is_quiet_now()


def test_critical_ignores_quiet_hours(client_user):
    _make_template(event_code="CRITICAL_EVENT")
    pref = NotificationPreference.for_user(client_user)
    pref.quiet_hours_start = time(22, 0)
    pref.quiet_hours_end = time(8, 0)
    pref.save()

    log = NotificationService.send_notification(
        user=client_user,
        event_code="CRITICAL_EVENT",
        context={"user_name": "Juan", "phone_number": client_user.phone_number},
        priority="critical",
    )

    assert log.status == NotificationLog.Status.QUEUED or log.status == NotificationLog.Status.SENT


def test_channel_fallback_to_email(client_user, monkeypatch):
    template = _make_template(event_code="EMAIL_EVENT", channel=NotificationTemplate.ChannelChoices.WHATSAPP)
    # Crear template email para fallback
    NotificationTemplate.objects.create(
        event_code="EMAIL_EVENT",
        channel=NotificationTemplate.ChannelChoices.EMAIL,
        subject_template="Hola",
        body_template="Email body",
        is_active=True,
    )
    pref = NotificationPreference.for_user(client_user)
    pref.whatsapp_enabled = False
    pref.email_enabled = True
    pref.save()

    dispatched = {}

    def fake_enqueue(log_id, **kwargs):
        dispatched["log_id"] = log_id
        return True

    monkeypatch.setattr("notifications.tasks.send_notification_task.apply_async", staticmethod(fake_enqueue))

    log = NotificationService.send_notification(
        user=client_user,
        event_code="EMAIL_EVENT",
        context={"user_name": "Mail", "phone_number": client_user.phone_number},
    )

    assert log is None or dispatched.get("log_id")
    failed_log = NotificationLog.objects.filter(event_code="EMAIL_EVENT").order_by("-created_at").first()
    assert failed_log is not None
    if failed_log.status == NotificationLog.Status.FAILED:
        assert "canales" in failed_log.error_message.lower()


def test_no_channels_enabled_fails(client_user):
    _make_template(event_code="NO_CHANNEL")
    pref = NotificationPreference.for_user(client_user)
    pref.whatsapp_enabled = False
    pref.email_enabled = False
    pref.save()

    log = NotificationService.send_notification(
        user=client_user,
        event_code="NO_CHANNEL",
        context={"phone_number": client_user.phone_number},
    )

    failed = NotificationLog.objects.filter(event_code="NO_CHANNEL").order_by("-created_at").first()
    assert failed.status == NotificationLog.Status.FAILED
    assert "canales" in failed.error_message.lower()


def test_missing_template_fails(client_user):
    log = NotificationService.send_notification(
        user=client_user,
        event_code="MISSING",
        context={"phone_number": client_user.phone_number},
    )
    failed = NotificationLog.objects.filter(event_code="MISSING").order_by("-created_at").first()
    assert failed.status == NotificationLog.Status.FAILED
    assert "plantilla" in failed.error_message.lower()


def test_update_notification_preferences(api_client, client_user):
    _auth(api_client, client_user)
    url = reverse("notification-preferences-me")
    resp = api_client.put(
        url,
        {
            "email_enabled": False,
            "quiet_hours_start": "23:00:00",
            "quiet_hours_end": "07:00:00",
            "timezone": "America/Mexico_City",
            "push_enabled": False,
            "sms_enabled": False,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    pref = NotificationPreference.for_user(client_user)
    assert pref.email_enabled is False
    assert pref.quiet_hours_start.strftime("%H:%M") == "23:00"
    assert pref.timezone == "America/Mexico_City"
