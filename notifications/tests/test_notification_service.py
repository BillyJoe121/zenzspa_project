import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import time
from notifications.services import NotificationService
from notifications.models import NotificationTemplate, NotificationLog, NotificationPreference
from users.models import CustomUser

@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        phone_number="+573001234567",
        email="test@example.com",
        password="password",
        first_name="Test User"
    )

@pytest.fixture
def whatsapp_template(db):
    return NotificationTemplate.objects.create(
        event_code="TEST_EVENT",
        channel=NotificationTemplate.ChannelChoices.WHATSAPP,
        body_template="Hello {{ name }}",
        is_active=True
    )

@pytest.mark.django_db
class TestNotificationService:
    def test_send_notification_success(self, user, whatsapp_template):
        with patch('notifications.tasks.send_notification_task.apply_async') as mock_task:
            log = NotificationService.send_notification(
                user=user,
                event_code="TEST_EVENT",
                context={"name": "World"}
            )
            
            assert log is not None
            assert log.status == NotificationLog.Status.QUEUED
            assert log.payload['body'] == "Hello World"
            mock_task.assert_called_once()

    def test_send_notification_anonymous_success(self, whatsapp_template):
        with patch('notifications.tasks.send_notification_task.apply_async') as mock_task:
            log = NotificationService.send_notification(
                user=None,
                event_code="TEST_EVENT",
                context={"name": "Stranger", "phone_number": "+573000000000"}
            )
            
            assert log is not None
            assert log.user is None
            assert log.metadata['phone_number'] == "+573000000000"
            assert log.payload['body'] == "Hello Stranger"
            mock_task.assert_called_once()

    def test_send_notification_anonymous_missing_phone(self, whatsapp_template):
        log = NotificationService.send_notification(
            user=None,
            event_code="TEST_EVENT",
            context={"name": "Stranger"}
        )
        
        assert log is None
        assert NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).exists()
        failed_log = NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).first()
        assert "phone_number" in failed_log.error_message

    def test_send_notification_missing_template(self, user):
        log = NotificationService.send_notification(
            user=user,
            event_code="NON_EXISTENT_EVENT",
            context={}
        )
        
        assert log is None
        assert NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).exists()
        failed_log = NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).first()
        assert "No existe plantilla" in failed_log.error_message

    def test_send_notification_user_disabled_channel(self, user, whatsapp_template):
        pref = NotificationPreference.for_user(user)
        pref.whatsapp_enabled = False
        pref.save()
        
        log = NotificationService.send_notification(
            user=user,
            event_code="TEST_EVENT",
            context={"name": "World"}
        )
        
        assert log is None
        assert NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).exists()
        failed_log = NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).first()
        assert "no tiene canales habilitados" in failed_log.error_message

    def test_send_notification_quiet_hours(self, user, whatsapp_template):
        pref = NotificationPreference.for_user(user)
        # Set quiet hours to cover current time
        now = timezone.now().astimezone(pref.tzinfo)
        start = (now - timezone.timedelta(hours=1)).time()
        end = (now + timezone.timedelta(hours=1)).time()
        pref.quiet_hours_start = start
        pref.quiet_hours_end = end
        pref.save()
        
        with patch('notifications.tasks.send_notification_task.apply_async') as mock_task:
            log = NotificationService.send_notification(
                user=user,
                event_code="TEST_EVENT",
                context={"name": "World"},
                priority="high" # Not critical
            )
            
            assert log is not None
            assert log.status == NotificationLog.Status.SILENCED
            mock_task.assert_called_once()
            args, kwargs = mock_task.call_args
            assert 'eta' in kwargs

    def test_send_notification_critical_bypasses_quiet_hours(self, user, whatsapp_template):
        pref = NotificationPreference.for_user(user)
        now = timezone.now().astimezone(pref.tzinfo)
        start = (now - timezone.timedelta(hours=1)).time()
        end = (now + timezone.timedelta(hours=1)).time()
        pref.quiet_hours_start = start
        pref.quiet_hours_end = end
        pref.save()
        
        with patch('notifications.tasks.send_notification_task.apply_async') as mock_task:
            log = NotificationService.send_notification(
                user=user,
                event_code="TEST_EVENT",
                context={"name": "World"},
                priority="critical"
            )
            
            assert log is not None
            assert log.status == NotificationLog.Status.QUEUED
            mock_task.assert_called_once()
            args, kwargs = mock_task.call_args
            assert 'eta' not in kwargs

    def test_sanitize_context(self):
        context = {
            "safe": "value",
            "unsafe": "value\x00with\x1fcontrol",
            "long": "a" * 1000
        }
        sanitized = NotificationService._sanitize_context(context)
        
        assert sanitized["safe"] == "value"
        assert "\x00" not in sanitized["unsafe"]
        assert len(sanitized["long"]) == 500

    def test_render_error(self, user):
        # Template with syntax error
        NotificationTemplate.objects.create(
            event_code="BAD_TEMPLATE",
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            body_template="{% if %}", # Invalid syntax
            is_active=True
        )
        
        log = NotificationService.send_notification(
            user=user,
            event_code="BAD_TEMPLATE",
            context={"name": "World"}
        )
        
        assert log is None
        assert NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).exists()
        failed_log = NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).first()
        assert "Template inválido" in failed_log.error_message
