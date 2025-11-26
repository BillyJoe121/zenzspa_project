import pytest
from django.core import mail
from django.utils import timezone
from model_bakery import baker

from bot.alerts import SuspiciousActivityAlertService, AutoBlockService
from bot.models import (
    BotConfiguration,
    SuspiciousActivity,
    IPBlocklist,
    BotConversationLog,
    AnonymousUser,
)
from users.models import CustomUser


@pytest.mark.django_db
def test_get_admin_emails_fallback_to_settings(settings):
    settings.ADMINS = [("Root", "root@example.com")]
    baker.make(CustomUser, role=CustomUser.Role.CLIENT, email="client@test.com")

    emails = SuspiciousActivityAlertService.get_admin_emails()

    assert emails == ["root@example.com"]


@pytest.mark.django_db
def test_get_admin_emails_returns_admins_and_superusers():
    admin_user = baker.make(
        CustomUser, role=CustomUser.Role.ADMIN, email="admin@test.com", is_active=True
    )
    superuser = baker.make(
        CustomUser, is_superuser=True, email="super@test.com", is_active=True
    )
    baker.make(
        CustomUser,
        role=CustomUser.Role.ADMIN,
        email="inactive@test.com",
        is_active=False,
    )

    emails = SuspiciousActivityAlertService.get_admin_emails()

    assert set(emails) == {admin_user.email, superuser.email}


@pytest.mark.django_db
def test_send_critical_activity_alert_sends_email(bot_config, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    baker.make(
        CustomUser, role=CustomUser.Role.ADMIN, email="alert@test.com", is_active=True
    )
    anon = baker.make(AnonymousUser, ip_address="10.0.0.1")
    activity = baker.make(
        SuspiciousActivity,
        anonymous_user=anon,
        ip_address="10.0.0.1",
        activity_type=SuspiciousActivity.ActivityType.JAILBREAK_ATTEMPT,
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        description="Intento crítico",
    )

    SuspiciousActivityAlertService.send_critical_activity_alert(activity)

    assert len(mail.outbox) == 1
    assert "ALERTA" in mail.outbox[0].subject
    assert activity.ip_address in mail.outbox[0].body


@pytest.mark.django_db
def test_send_critical_activity_alert_respects_disabled_flag(bot_config, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    bot_config.enable_critical_alerts = False
    bot_config.save()
    baker.make(CustomUser, role=CustomUser.Role.ADMIN, email="alert@test.com")
    anon = baker.make(AnonymousUser, ip_address="10.0.0.2")
    activity = baker.make(
        SuspiciousActivity,
        anonymous_user=anon,
        ip_address="10.0.0.2",
        activity_type=SuspiciousActivity.ActivityType.MALICIOUS_CONTENT,
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        description="Debe ignorarse",
    )

    SuspiciousActivityAlertService.send_critical_activity_alert(activity)

    assert mail.outbox == []


@pytest.mark.django_db
def test_send_daily_security_report_collects_stats(bot_config, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    baker.make(CustomUser, role=CustomUser.Role.ADMIN, email="alert@test.com")
    anon = baker.make(AnonymousUser, ip_address="8.8.8.8")
    baker.make(
        SuspiciousActivity,
        anonymous_user=anon,
        ip_address="8.8.8.8",
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        activity_type=SuspiciousActivity.ActivityType.REPETITIVE_MESSAGES,
    )
    baker.make(
        IPBlocklist, ip_address="8.8.8.8", reason=IPBlocklist.BlockReason.ABUSE
    )
    baker.make(
        BotConversationLog,
        anonymous_user=anon,
        ip_address="8.8.8.8",
        was_blocked=True,
        tokens_used=25,
    )

    SuspiciousActivityAlertService.send_daily_security_report()

    assert len(mail.outbox) == 1
    assert "REPORTE DIARIO" in mail.outbox[0].body
    assert "8.8.8.8" in mail.outbox[0].body


@pytest.mark.django_db
def test_auto_block_returns_false_without_config():
    BotConfiguration.objects.all().delete()

    was_blocked, block = AutoBlockService.check_and_auto_block(ip_address="2.2.2.2")

    assert was_blocked is False
    assert block is None


@pytest.mark.django_db
def test_auto_block_blocks_when_threshold_met(bot_config, mocker):
    bot_config.enable_auto_block = True
    bot_config.auto_block_critical_threshold = 1
    bot_config.save()
    anon = baker.make(AnonymousUser, ip_address="3.3.3.3")
    baker.make(
        SuspiciousActivity,
        anonymous_user=anon,
        ip_address="3.3.3.3",
        severity=SuspiciousActivity.SeverityLevel.CRITICAL,
        activity_type=SuspiciousActivity.ActivityType.MALICIOUS_CONTENT,
        created_at=timezone.now(),
    )
    notifier = mocker.patch(
        "bot.alerts.SuspiciousActivityAlertService.send_auto_block_notification"
    )

    was_blocked, block = AutoBlockService.check_and_auto_block(
        anonymous_user=anon, ip_address="3.3.3.3"
    )

    assert was_blocked is True
    assert block.ip_address == "3.3.3.3"
    notifier.assert_called_once()


@pytest.mark.django_db
def test_auto_block_returns_existing_block(bot_config):
    block = baker.make(
        IPBlocklist, ip_address="4.4.4.4", is_active=True, expires_at=None
    )

    was_blocked, returned = AutoBlockService.check_and_auto_block(
        ip_address=block.ip_address
    )

    assert was_blocked is False
    assert returned == block
