import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils import timezone
from notifications.admin import NotificationPreferenceAdmin, NotificationTemplateAdmin, NotificationLogAdmin
from notifications.models import NotificationPreference, NotificationTemplate, NotificationLog
from users.models import CustomUser
from datetime import time, timedelta

class MockRequest:
    pass

class MockSuperUser:
    def has_perm(self, perm):
        return True

@pytest.fixture
def site():
    return AdminSite()

@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        email="admin@example.com",
        password="password",
        phone_number="+573001234567",
        is_staff=True,
        is_superuser=True
    )

@pytest.fixture
def rf():
    return RequestFactory()

@pytest.mark.django_db
class TestNotificationPreferenceAdmin:
    def test_quiet_hours_range(self, site, user):
        pref = NotificationPreference.objects.create(
            user=user,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0)
        )
        ma = NotificationPreferenceAdmin(NotificationPreference, site)
        assert ma.quiet_hours_range(pref) == "22:00 - 08:00"

        pref.quiet_hours_start = None
        assert ma.quiet_hours_range(pref) == "-"

@pytest.mark.django_db
class TestNotificationTemplateAdmin:
    def test_methods(self, site):
        ma = NotificationTemplateAdmin(NotificationTemplate, site)
        
        # Active template
        tpl = NotificationTemplate.objects.create(
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            is_active=True,
            body_template="Hello {{ name }}"
        )
        
        assert "Activa" in ma.is_active_colored(tpl)
        assert "Hello {{ name }}" in ma.preview_link(tpl)
        # format_html escapes braces, so we check for the content or escaped version
        # Or just check for parts of it
        assert "Hello" in ma.preview_display(tpl)
        assert "name" in ma.preview_display(tpl)
        assert "Válida" in ma.validation_status(tpl)
        assert "0 envíos" in ma.usage_count(tpl)
        assert "Estadísticas de Uso" in ma.usage_stats(tpl)

        # Inactive template
        tpl.is_active = False
        tpl.save()
        assert "Inactiva" in ma.is_active_colored(tpl)

        # Long template
        tpl.body_template = "A" * 100
        tpl.save()
        assert "..." in ma.preview_link(tpl)

        # Invalid template (mocking exception in full_clean if needed, but here we can just rely on validation_status catching it if we force an invalid state or just trust the method logic)
        # Actually validation_status calls full_clean. Let's try to make it fail.
        # But full_clean might pass if fields are valid.
        # We can mock full_clean to raise exception
        from django.core.exceptions import ValidationError
        from unittest.mock import patch
        
        with patch.object(NotificationTemplate, 'full_clean', side_effect=ValidationError("Error")):
            assert "Inválida" in ma.validation_status(tpl)

@pytest.mark.django_db
class TestNotificationLogAdmin:
    def test_methods(self, site, user):
        ma = NotificationLogAdmin(NotificationLog, site)
        
        log = NotificationLog.objects.create(
            user=user,
            event_code="TEST",
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SENT,
            metadata={"attempts": 1, "max_attempts": 3},
            payload={"msg": "hi"}
        )
        
        assert "green" in ma.status_colored(log)
        assert "1/3" in ma.attempts_display(log)
        assert "attempts" in ma.metadata_display(log)
        assert "msg" in ma.payload_display(log)
        assert user.email in ma.user_display(log)

        # Failed status
        log.status = NotificationLog.Status.FAILED
        log.metadata["attempts"] = 3
        log.save()
        assert "red" in ma.status_colored(log)
        assert "red" in ma.attempts_display(log) # Max attempts reached

        # No user
        log.user = None
        log.save()
        assert "-" in ma.user_display(log)

    def test_changelist_view(self, site, rf, user):
        ma = NotificationLogAdmin(NotificationLog, site)
        request = rf.get("/")
        request.user = user
        
        # Use a fixed time to avoid timezone issues (noon UTC is safe for Western Hemisphere)
        from datetime import datetime, timezone as dt_timezone
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        
        from unittest.mock import patch
        with patch("django.utils.timezone.now", return_value=fixed_now):
            # Create logs with fixed time
            NotificationLog.objects.create(
                event_code="A", 
                channel=NotificationTemplate.ChannelChoices.WHATSAPP, 
                status=NotificationLog.Status.SENT,
                created_at=fixed_now
            )
            NotificationLog.objects.create(
                event_code="B", 
                channel=NotificationTemplate.ChannelChoices.WHATSAPP, 
                status=NotificationLog.Status.FAILED,
                created_at=fixed_now
            )
            
            # Ensure created_at is exactly fixed_now
            NotificationLog.objects.all().update(created_at=fixed_now)
            
            response = ma.changelist_view(request)
            ctx = response.context_data
            
            assert ctx['today_stats']['total'] >= 2
            assert 'channel_stats' in ctx
