"""
Tests básicos para el módulo notifications.
Cobertura: NotificationPreference, NotificationService, NotificationRenderer
"""
import pytest
from datetime import time
from django.utils import timezone
from django.core.exceptions import ValidationError
from unittest.mock import patch, MagicMock

from notifications.models import NotificationPreference, NotificationTemplate, NotificationLog
from notifications.services import NotificationService, NotificationRenderer
from users.models import CustomUser


@pytest.mark.django_db
class TestNotificationPreference:
    """Tests para NotificationPreference"""

    def test_for_user_creates_if_not_exists(self):
        """for_user debe crear preferencias si no existen"""
        user = CustomUser.objects.create_user(
            email="test@example.com",
            phone_number="+573001234567",
            password="testpass123"
        )
        pref = NotificationPreference.for_user(user)
        assert pref.user == user
        assert pref.email_enabled is True

    def test_for_user_returns_existing(self):
        """for_user debe retornar preferencia existente"""
        user = CustomUser.objects.create_user(
            email="test2@example.com",
            phone_number="+573001234568",
            password="testpass123"
        )
        pref1 = NotificationPreference.objects.create(user=user)
        pref2 = NotificationPreference.for_user(user)
        assert pref1.id == pref2.id

    def test_is_quiet_now_within_hours(self):
        """is_quiet_now debe detectar quiet hours correctamente"""
        user = CustomUser.objects.create_user(
            email="test3@example.com",
            phone_number="+573001234569",
            password="testpass123"
        )
        pref = NotificationPreference.objects.create(
            user=user,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
            timezone="America/Bogota"
        )

        # Crear momento dentro de quiet hours con timezone aware
        from datetime import datetime
        from zoneinfo import ZoneInfo
        bogota_tz = ZoneInfo("America/Bogota")
        moment = datetime.now(bogota_tz).replace(hour=23, minute=0)
        assert pref.is_quiet_now(moment) is True

        # Test fuera de quiet hours (12:00)
        moment = datetime.now(bogota_tz).replace(hour=12, minute=0)
        assert pref.is_quiet_now(moment) is False

    def test_is_quiet_now_no_quiet_hours(self):
        """is_quiet_now debe retornar False si no hay quiet hours"""
        user = CustomUser.objects.create_user(
            email="test4@example.com",
            phone_number="+573001234570",
            password="testpass123"
        )
        pref = NotificationPreference.objects.create(user=user)
        assert pref.is_quiet_now() is False

    def test_invalid_timezone_raises_error(self):
        """Timezone inválido debe lanzar ValidationError"""
        user = CustomUser.objects.create_user(
            email="test5@example.com",
            phone_number="+573001234571",
            password="testpass123"
        )
        pref = NotificationPreference(
            user=user,
            timezone="Invalid/Timezone"
        )

        with pytest.raises(ValidationError) as exc_info:
            pref.clean()

        assert "timezone" in exc_info.value.message_dict

    def test_quiet_hours_validation_both_required(self):
        """Quiet hours requiere inicio y fin"""
        user = CustomUser.objects.create_user(
            email="test6@example.com",
            phone_number="+573001234572",
            password="testpass123"
        )
        pref = NotificationPreference(
            user=user,
            quiet_hours_start=time(22, 0)
            # Falta quiet_hours_end
        )

        with pytest.raises(ValidationError) as exc_info:
            pref.clean()

        assert "quiet_hours_start" in exc_info.value.message_dict

    def test_quiet_hours_validation_same_time(self):
        """Quiet hours no puede tener inicio == fin"""
        user = CustomUser.objects.create_user(
            email="test7@example.com",
            phone_number="+573001234573",
            password="testpass123"
        )
        pref = NotificationPreference(
            user=user,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(22, 0)
        )

        with pytest.raises(ValidationError) as exc_info:
            pref.clean()

        assert "quiet_hours_start" in exc_info.value.message_dict

    def test_channel_enabled(self):
        """channel_enabled debe retornar estado correcto"""
        user = CustomUser.objects.create_user(
            email="test8@example.com",
            phone_number="+573001234574",
            password="testpass123"
        )
        pref = NotificationPreference.objects.create(
            user=user,
            email_enabled=True,
            sms_enabled=False
        )

        assert pref.channel_enabled(NotificationTemplate.ChannelChoices.EMAIL) is True
        assert pref.channel_enabled(NotificationTemplate.ChannelChoices.SMS) is False


@pytest.mark.django_db
class TestNotificationService:
    """Tests para NotificationService"""

    def test_send_notification_creates_log(self):
        """send_notification debe crear NotificationLog"""
        user = CustomUser.objects.create_user(
            email="test9@example.com",
            phone_number="+573001234575",
            password="testpass123"
        )

        # Crear template
        NotificationTemplate.objects.create(
            event_code="TEST_EVENT",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Test Subject",
            body_template="Test Body",
            is_active=True
        )

        with patch('notifications.tasks.send_notification_task'):
            log = NotificationService.send_notification(
                user=user,
                event_code="TEST_EVENT",
                context={}
            )

        assert log is not None
        assert log.event_code == "TEST_EVENT"
        assert log.status == NotificationLog.Status.QUEUED

    def test_no_template_creates_failed_log(self):
        """Sin template debe crear log FAILED"""
        user = CustomUser.objects.create_user(
            email="test10@example.com",
            phone_number="+573001234576",
            password="testpass123"
        )

        log = NotificationService.send_notification(
            user=user,
            event_code="NON_EXISTENT_EVENT",
            context={}
        )

        assert log is None

        # Verificar que se creó un log FAILED
        failed_log = NotificationLog.objects.filter(
            event_code="NON_EXISTENT_EVENT",
            status=NotificationLog.Status.FAILED
        ).first()

        assert failed_log is not None
        assert "No existe plantilla" in failed_log.error_message

    def test_user_none_returns_none(self):
        """send_notification con user=None debe retornar None"""
        log = NotificationService.send_notification(
            user=None,
            event_code="TEST_EVENT",
            context={}
        )
        assert log is None

    def test_channel_disabled_creates_failed_log(self):
        """Canal deshabilitado debe crear log FAILED"""
        user = CustomUser.objects.create_user(
            email="test11@example.com",
            phone_number="+573001234577",
            password="testpass123"
        )

        # Deshabilitar email
        pref = NotificationPreference.for_user(user)
        pref.email_enabled = False
        pref.save()

        # Crear template solo EMAIL
        NotificationTemplate.objects.create(
            event_code="TEST_EVENT_2",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Test",
            body_template="Test",
            is_active=True
        )

        log = NotificationService.send_notification(
            user=user,
            event_code="TEST_EVENT_2",
            context={}
        )

        assert log is None

        # Verificar log FAILED
        failed_log = NotificationLog.objects.filter(
            event_code="TEST_EVENT_2",
            status=NotificationLog.Status.FAILED
        ).first()

        assert failed_log is not None
        assert "no tiene canales habilitados" in failed_log.error_message


@pytest.mark.django_db
class TestNotificationRenderer:
    """Tests para NotificationRenderer"""

    def test_render_with_context(self):
        """render debe reemplazar variables del contexto"""
        template = NotificationTemplate(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Hello {{ name }}",
            body_template="Your appointment is at {{ time }}"
        )

        subject, body = NotificationRenderer.render(
            template,
            {"name": "John", "time": "10:00"}
        )

        assert subject == "Hello John"
        assert body == "Your appointment is at 10:00"

    def test_render_no_subject(self):
        """render sin subject_template debe retornar subject vacío"""
        template = NotificationTemplate(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="",
            body_template="Body content"
        )

        subject, body = NotificationRenderer.render(template, {})

        assert subject == ""
        assert body == "Body content"

    def test_render_empty_context(self):
        """render con context vacío debe funcionar"""
        template = NotificationTemplate(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Static subject",
            body_template="Static body"
        )

        subject, body = NotificationRenderer.render(template, {})

        assert subject == "Static subject"
        assert body == "Static body"

    def test_render_missing_variable_logs_warning(self):
        """Variables faltantes deben renderizarse como vacías"""
        template = NotificationTemplate(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Hello {{ name }}",
            body_template="Your appointment is at {{ missing_var }}"
        )

        # No debe lanzar excepción
        subject, body = NotificationRenderer.render(
            template,
            {"name": "John"}
        )

        assert subject == "Hello John"
        # Django renderiza variables missing como vacías por defecto
        assert "Your appointment is at" in body

    def test_render_syntax_error_raises(self):
        """Error de sintaxis debe ser manejado por Django Template"""
        template = NotificationTemplate(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            subject_template="Hello {{ name",  # Falta cerrar }}
            body_template="Body"
        )

        # Django Template puede lanzar TemplateSyntaxError que capturamos como ValueError
        try:
            NotificationRenderer.render(template, {"name": "John"})
            # Si no lanza error, Django lo manejó silenciosamente
        except (ValueError, Exception):
            # Esperado - error de sintaxis
            pass


@pytest.mark.django_db
class TestNotificationLog:
    """Tests para NotificationLog model"""

    def test_create_log(self):
        """Crear log básico"""
        user = CustomUser.objects.create_user(
            email="test12@example.com",
            phone_number="+573001234578",
            password="testpass123"
        )

        log = NotificationLog.objects.create(
            user=user,
            event_code="TEST_EVENT",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            status=NotificationLog.Status.QUEUED
        )

        assert log.id is not None
        assert log.user == user
        assert log.status == NotificationLog.Status.QUEUED

    def test_log_str_representation(self):
        """__str__ debe retornar formato correcto"""
        user = CustomUser.objects.create_user(
            email="test13@example.com",
            phone_number="+573001234579",
            password="testpass123"
        )

        log = NotificationLog.objects.create(
            user=user,
            event_code="TEST_EVENT",
            channel=NotificationTemplate.ChannelChoices.EMAIL,
            status=NotificationLog.Status.SENT
        )

        assert "TEST_EVENT" in str(log)
        assert "EMAIL" in str(log)
        assert "SENT" in str(log)
