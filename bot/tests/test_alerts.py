import pytest
from django.utils import timezone
from model_bakery import baker
from unittest.mock import patch

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
@patch("bot.alerts.NotificationService.send_notification")
def test_send_critical_activity_alert_sends_whatsapp(mock_send, bot_config):
    baker.make(
        CustomUser,
        role=CustomUser.Role.ADMIN,
        phone_number=bot_config.admin_phone,
        is_active=True,
        is_staff=True,
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

    mock_send.assert_called_once()


@pytest.mark.django_db
@patch("bot.alerts.NotificationService.send_notification")
def test_send_critical_activity_alert_respects_disabled_flag(mock_send, bot_config):
    bot_config.enable_critical_alerts = False
    bot_config.save()
    baker.make(
        CustomUser,
        role=CustomUser.Role.ADMIN,
        phone_number=bot_config.admin_phone,
        is_active=True,
        is_staff=True,
    )
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

    mock_send.assert_not_called()


@pytest.mark.django_db
@patch("bot.alerts.NotificationService.send_notification")
def test_send_daily_security_report_collects_stats(mock_send, bot_config):
    baker.make(
        CustomUser,
        role=CustomUser.Role.ADMIN,
        phone_number=bot_config.admin_phone,
        is_active=True,
        is_staff=True,
    )
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

    mock_send.assert_called_once()


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
