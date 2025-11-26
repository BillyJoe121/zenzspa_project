import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from unittest import mock

from core import admin as core_admin
from core.models import GlobalSettings, AuditLog


class DummyAdminSite(AdminSite):
    pass


@pytest.mark.django_db
def test_audit_log_admin_disallows_add_and_delete():
    site = DummyAdminSite()
    admin_obj = core_admin.AuditLogAdmin(AuditLog, site)
    request = RequestFactory().get("/")

    assert admin_obj.has_add_permission(request) is False
    assert admin_obj.has_delete_permission(request) is False


@pytest.mark.django_db
def test_global_settings_admin_add_permission_respects_singleton():
    site = DummyAdminSite()
    admin_obj = core_admin.GlobalSettingsAdmin(GlobalSettings, site)
    request = RequestFactory().get("/")

    # Sin instancia creada, debe permitir agregar
    GlobalSettings.objects.all().delete()
    assert admin_obj.has_add_permission(request) is True

    # Con instancia existente, ya no permite agregar
    instance = GlobalSettings()
    instance.save()
    assert admin_obj.has_add_permission(request) is False
    assert admin_obj.has_delete_permission(request, obj=instance) is False


@pytest.mark.django_db
def test_global_settings_admin_save_model_calls_full_clean(monkeypatch):
    """Test que save_model llama full_clean antes de guardar"""
    from django.core.cache import cache

    site = DummyAdminSite()
    admin_obj = core_admin.GlobalSettingsAdmin(GlobalSettings, site)
    request = RequestFactory().post("/")
    obj = GlobalSettings.load()

    # Mock cache.set para evitar errores de serialización en tests
    cache_set_mock = mock.Mock()
    monkeypatch.setattr(cache, "set", cache_set_mock)

    # Mock full_clean para verificar que se llama
    full_clean_mock = mock.Mock()
    monkeypatch.setattr(obj, "full_clean", full_clean_mock)

    admin_obj.save_model(request, obj, form=None, change=True)

    # Verificar que full_clean fue llamado al menos una vez
    # (se llama en admin.save_model y en model.save)
    assert full_clean_mock.call_count >= 1
