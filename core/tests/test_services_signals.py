from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command

from core import services, signals, selectors
from core.models import AuditLog, GlobalSettings
from core.caching import CacheKeys


@pytest.mark.django_db
def test_get_setting_handles_missing_and_exceptions(monkeypatch):
    cache.clear()
    settings_obj = GlobalSettings.load()
    settings_obj.appointment_buffer_time = 15
    settings_obj.save()

    assert services.get_setting("appointment_buffer_time") == 15
    assert services.get_setting("does_not_exist", default="fallback") == "fallback"

    def raise_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(services, "GlobalSettings", type("FakeGS", (), {"load": staticmethod(raise_error)}))
    assert services.get_setting("appointment_buffer_time", default="safe") == "safe"


@pytest.mark.django_db
def test_admin_flag_non_grata_creates_audit_log(admin_user, client_user):
    cache.clear()
    created = services.admin_flag_non_grata(admin_user, client_user, details={"reason": "test"})
    assert created is True
    log = AuditLog.objects.latest("created_at")
    assert log.action == AuditLog.Action.FLAG_NON_GRATA
    assert log.admin_user == admin_user
    assert log.target_user == client_user
    assert "test" in str(log.details)


def test_invalidate_global_settings_cache_signal():
    """Test que el signal invalida la clave correcta de GlobalSettings"""
    cache.set(CacheKeys.GLOBAL_SETTINGS, "dummy", timeout=60)
    signals.invalidate_global_settings_cache(sender=GlobalSettings)
    assert cache.get(CacheKeys.GLOBAL_SETTINGS) is None


def test_rebuild_cache_command_clears_known_keys():
    """Test que rebuild_cache limpia las claves correctas usando CacheKeys"""
    keys = [
        CacheKeys.SERVICES,
        CacheKeys.CATEGORIES,
        CacheKeys.PACKAGES,
        CacheKeys.GLOBAL_SETTINGS,
    ]
    for key in keys:
        cache.set(key, "value", timeout=60)

    out = StringIO()
    call_command("rebuild_cache", stdout=out)

    assert all(cache.get(key) is None for key in keys)
    output_text = out.getvalue()
    for key in keys:
        assert key in output_text


@pytest.mark.django_db
def test_selectors_list_audit_logs(admin_user, client_user):
    log = AuditLog.objects.create(
        action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
        admin_user=admin_user,
        target_user=client_user,
        details="selector-test",
    )
    all_logs = selectors.list_audit_logs()
    assert log in list(all_logs)

    target_logs = selectors.list_audit_logs_for_user(client_user.id)
    assert list(target_logs) == [log]
