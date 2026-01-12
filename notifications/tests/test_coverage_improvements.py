import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from notifications.models import NotificationLog, NotificationTemplate, NotificationPreference
from notifications.tasks import send_notification_task, check_upcoming_appointments_2h, cleanup_old_notification_logs
from notifications.whatsapp_service import WhatsAppService
from notifications.views import NotificationPreferenceView
from users.models import CustomUser
from spa.models import Appointment, ServiceCategory, Service
from datetime import timedelta
from rest_framework.test import APIClient

@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        phone_number="+573001112233",
        email="user@example.com",
        password="password",
        first_name="User"
    )

@pytest.fixture
def api_client():
    return APIClient()

@pytest.mark.django_db
class TestWhatsAppService:
    def test_validate_phone(self):
        assert WhatsAppService.validate_phone("+573001234567") is True
        assert WhatsAppService.validate_phone("3001234567") is False # Missing +
        assert WhatsAppService.validate_phone("+57300") is False # Too short
        assert WhatsAppService.validate_phone("+573001234567890123") is False # Too long
        assert WhatsAppService.validate_phone(None) is False

    @patch("notifications.whatsapp_service.settings")
    @patch("twilio.rest.Client")
    def test_send_message_success(self, mock_client, mock_settings):
        # Setup mocks
        mock_settings.TWILIO_ACCOUNT_SID = "ACxxx"
        mock_settings.TWILIO_AUTH_TOKEN = "token"
        mock_settings.TWILIO_WHATSAPP_FROM = "+14155238886"
        
        mock_message = MagicMock()
        mock_message.sid = "SMxxx"
        mock_client.return_value.messages.create.return_value = mock_message

        result = WhatsAppService.send_message("+573001234567", "Hello")
        
        assert result["success"] is True
        assert result["sid"] == "SMxxx"
        mock_client.return_value.messages.create.assert_called_once()

    @patch("notifications.whatsapp_service.settings")
    def test_send_message_missing_credentials(self, mock_settings):
        mock_settings.TWILIO_ACCOUNT_SID = None
        result = WhatsAppService.send_message("+573001234567", "Hello")
        assert result["success"] is False
        assert "Credenciales Twilio faltantes" in result["error"]

    @patch("notifications.whatsapp_service.settings")
    @patch("twilio.rest.Client")
    def test_send_template_message_success(self, mock_client, mock_settings):
        # Setup mocks
        mock_settings.TWILIO_ACCOUNT_SID = "ACxxx"
        mock_settings.TWILIO_AUTH_TOKEN = "token"
        mock_settings.TWILIO_WHATSAPP_FROM = "+14155238886"
        
        mock_message = MagicMock()
        mock_message.sid = "SMxxx"
        mock_client.return_value.messages.create.return_value = mock_message

        result = WhatsAppService.send_template_message(
            to_phone="+573001234567",
            content_sid="HXxxx",
            content_variables={"1": "User"}
        )
        
        assert result["success"] is True
        assert result["sid"] == "SMxxx"

@pytest.mark.django_db
class TestNotificationTasks:
    def test_send_notification_task_log_not_found(self):
        assert send_notification_task(9999) == "Log desaparecido"

    def test_send_notification_task_already_sent(self, user):
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SENT
        )
        assert send_notification_task(log.id) == "Ya enviado"

    @patch("notifications.tasks._dispatch_channel")
    def test_send_notification_task_success(self, mock_dispatch, user):
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.QUEUED
        )
        result = send_notification_task(log.id)
        assert result == "Enviado"
        log.refresh_from_db()
        assert log.status == NotificationLog.Status.SENT
        assert log.sent_at is not None

    @patch("notifications.tasks._dispatch_channel")
    def test_send_notification_task_retry(self, mock_dispatch, user):
        mock_dispatch.side_effect = Exception("Twilio Error")
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.QUEUED,
            metadata={"max_attempts": 3}
        )
        
        # First attempt
        with patch("notifications.tasks.send_notification_task.apply_async") as mock_retry:
            result = send_notification_task(log.id)
            assert "retry_scheduled" in result
            log.refresh_from_db()
            assert log.status == NotificationLog.Status.QUEUED
            assert log.metadata["attempts"] == 1
            mock_retry.assert_called_once()

    @patch("notifications.tasks._dispatch_channel")
    def test_send_notification_task_dead_letter(self, mock_dispatch, user):
        mock_dispatch.side_effect = Exception("Fatal Error")
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.QUEUED,
            metadata={"max_attempts": 1, "attempts": 1} # Already at max
        )
        
        result = send_notification_task(log.id)
        assert result == "dead_letter"
        log.refresh_from_db()
        assert log.status == NotificationLog.Status.FAILED
        assert log.metadata["dead_letter"] is True

    def test_send_notification_task_silenced(self, user):
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SILENCED
        )
        send_notification_task(log.id)
        log.refresh_from_db()
        assert log.status == NotificationLog.Status.QUEUED

    def test_send_notification_task_fallback(self, user):
        log = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.QUEUED,
            metadata={
                "max_attempts": 2, # Increase to allow retry/fallback logic before DLQ
                "attempts": 0, 
                "fallback": ["email"],
                "context": {"foo": "bar"}
            }
        )
        
        # Mock dispatch to fail
        with patch("notifications.tasks._dispatch_channel", side_effect=Exception("Fail")):
            with patch("notifications.services.NotificationService.send_notification") as mock_send:
                send_notification_task(log.id)
                
                log.refresh_from_db()
                assert log.metadata.get("fallback_attempted") is True
                mock_send.assert_called_with(
                    user=user,
                    event_code=log.event_code,
                    context={"foo": "bar"},
                    priority=log.priority,
                    channel_override="email",
                    fallback_channels=[]
                )

    def test_dispatch_channel_logic(self, user):
        from notifications.tasks import _dispatch_channel
        
        # SMS (Not implemented)
        log_sms = NotificationLog(user=user, channel=NotificationTemplate.ChannelChoices.SMS)
        with pytest.raises(ValueError, match="Canal SMS no disponible"):
            _dispatch_channel(log_sms)

        # PUSH (Not implemented)
        log_push = NotificationLog(user=user, channel=NotificationTemplate.ChannelChoices.PUSH)
        with pytest.raises(ValueError, match="Canal PUSH no disponible"):
            _dispatch_channel(log_push)

        # Unknown
        log_unknown = NotificationLog(user=user, channel="unknown")
        with pytest.raises(ValueError, match="Canal desconocido"):
            _dispatch_channel(log_unknown)

        # WhatsApp - No phone
        user_no_phone = CustomUser.objects.create(email="nophone@example.com", password="pw", phone_number="")
        log_no_phone = NotificationLog(user=user_no_phone, channel=NotificationTemplate.ChannelChoices.WHATSAPP)
        with pytest.raises(ValueError, match="El usuario no tiene número de teléfono"):
            _dispatch_channel(log_no_phone)

        # WhatsApp - Invalid phone
        user.phone_number = "123"
        user.save()
        log_inv_phone = NotificationLog(user=user, channel=NotificationTemplate.ChannelChoices.WHATSAPP)
        with pytest.raises(ValueError, match="Número de teléfono inválido"):
            _dispatch_channel(log_inv_phone)

        # WhatsApp - Template configured
        user.phone_number = "+573001234567"
        user.save()
        log_wa = NotificationLog(
            user=user, 
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            event_code="TEST_CODE",
            payload={"subject": "S", "body": "B"},
            metadata={"context": {"name": "User"}}
        )
        
        # Patch where it is defined
        with patch("notifications.twilio_templates.is_template_configured", return_value=True):
            with patch("notifications.twilio_templates.get_template_config", return_value={"content_sid": "HX1", "variables": ["name"]}):
                with patch("notifications.whatsapp_service.WhatsAppService.send_template_message", return_value={"success": True}) as mock_send:
                    _dispatch_channel(log_wa)
                    mock_send.assert_called()

        # WhatsApp - Dynamic (Fallback)
        with patch("notifications.twilio_templates.is_template_configured", return_value=False):
            with patch("notifications.whatsapp_service.WhatsAppService.send_message", return_value={"success": True}) as mock_send:
                _dispatch_channel(log_wa)
                mock_send.assert_called()

        # WhatsApp - Error
        with patch("notifications.twilio_templates.is_template_configured", return_value=False):
            with patch("notifications.whatsapp_service.WhatsAppService.send_message", return_value={"success": False, "error": "Err"}):
                with pytest.raises(Exception, match="Err"):
                    _dispatch_channel(log_wa)

    def test_helpers(self, user):
        from notifications.tasks import user_id_display, mask_contact
        
        assert user_id_display(None) == "anon"
        assert mask_contact(None) == "***"
        assert mask_contact("a@b.com") == "***@b.com"
        assert mask_contact("long@email.com") == "l***g@email.com"
        assert mask_contact("123") == "***"
        assert mask_contact("12345") == "12***45"

    def test_cleanup_old_notification_logs(self, user):
        # Old sent log
        old_sent = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SENT,
            sent_at=timezone.now() - timedelta(days=91)
        )
        # Recent sent log
        recent_sent = NotificationLog.objects.create(
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SENT,
            sent_at=timezone.now() - timedelta(days=89)
        )
        
        result = cleanup_old_notification_logs()
        assert result["sent_deleted"] == 1
        assert not NotificationLog.objects.filter(id=old_sent.id).exists()
        assert NotificationLog.objects.filter(id=recent_sent.id).exists()

    @patch("notifications.services.NotificationService.send_notification")
    def test_check_upcoming_appointments_2h(self, mock_send, user):
        from spa.models import AppointmentItem
        
        # Setup appointment in 2 hours + 2 minutes
        start_time = timezone.now() + timedelta(hours=2, minutes=2)
        end_time = start_time + timedelta(minutes=60)
        
        service = Service.objects.create(
            name="Massage", 
            duration=60, 
            price=100,
            category=ServiceCategory.objects.create(name="Spa")
        )
        
        appointment = Appointment.objects.create(
            user=user,
            start_time=start_time,
            end_time=end_time,
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100
        )
        
        AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            duration=60,
            price_at_purchase=100
        )
        
        result = check_upcoming_appointments_2h()
        assert "1 recordatorios generados" in result
        mock_send.assert_called_once()

@pytest.mark.django_db
class TestNotificationViews:
    def test_notification_preference_view(self, api_client, user):
        api_client.force_authenticate(user=user)
        url = '/api/v1/notifications/preferences/me/'
        
        # Get
        response = api_client.get(url)
        assert response.status_code == 200
        assert "email_enabled" in response.data
        
        # Update
        response = api_client.patch(url, {"email_enabled": False})
        assert response.status_code == 200
        assert response.data["email_enabled"] is False
        
        pref = NotificationPreference.objects.get(user=user)
        assert pref.email_enabled is False
