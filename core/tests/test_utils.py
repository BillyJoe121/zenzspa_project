import types
from types import SimpleNamespace

import pytest
from django.core.cache import cache

from core import utils
from core.models import AuditLog


def test_get_client_ip_prefers_forwarded_for_when_trust_proxy_enabled(settings):
    """Con TRUST_PROXY=True, debe usar X-Forwarded-For"""
    settings.TRUST_PROXY = True
    request = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2", "REMOTE_ADDR": "127.0.0.1"})
    assert utils.get_client_ip(request) == "10.0.0.1"


def test_get_client_ip_ignores_forwarded_for_when_trust_proxy_disabled(settings):
    """Con TRUST_PROXY=False, debe ignorar X-Forwarded-For y usar REMOTE_ADDR"""
    settings.TRUST_PROXY = False
    request = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2", "REMOTE_ADDR": "192.168.1.100"})
    assert utils.get_client_ip(request) == "192.168.1.100"


def test_get_client_ip_defaults_to_remote_addr_when_no_trust_proxy(settings):
    """Sin TRUST_PROXY configurado, debe usar REMOTE_ADDR por defecto"""
    if hasattr(settings, 'TRUST_PROXY'):
        delattr(settings, 'TRUST_PROXY')
    request = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "10.0.0.1", "REMOTE_ADDR": "192.168.1.100"})
    assert utils.get_client_ip(request) == "192.168.1.100"


def test_cached_singleton_sets_and_reuses_cache():
    cache_key = "test:cached_singleton"
    cache.delete(cache_key)
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return "loaded-value"

    first = utils.cached_singleton(cache_key, timeout=60, loader=loader)
    second = utils.cached_singleton(cache_key, timeout=60, loader=loader)

    assert first == "loaded-value"
    assert second == "loaded-value"
    assert calls["count"] == 1  # loader solo debió llamarse una vez gracias al caché


def test_invalidate_removes_cache_key():
    cache_key = "test:invalidate"
    cache.set(cache_key, "value", timeout=60)
    utils.invalidate(cache_key)
    assert cache.get(cache_key) is None


@pytest.mark.django_db
def test_safe_audit_log_creates_entry(admin_user, client_user):
    entry = utils.safe_audit_log(
        action=AuditLog.Action.FLAG_NON_GRATA,
        admin_user=admin_user,
        target_user=client_user,
        details="Testing",
    )
    assert entry is not None
    assert entry.action == AuditLog.Action.FLAG_NON_GRATA
    assert entry.admin_user == admin_user
    assert entry.target_user == client_user


@pytest.mark.django_db
def test_safe_audit_log_swallows_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(AuditLog.objects, "create", boom)
    assert utils.safe_audit_log(action="ANY") is None


def test_retry_with_backoff_eventually_succeeds(monkeypatch):
    attempts = {"count": 0}
    sleep_calls = []

    monkeypatch.setattr(utils, "time", types.SimpleNamespace(sleep=lambda t: sleep_calls.append(t)))

    @utils.retry_with_backoff(max_retries=2, base_delay=0.1, max_delay=1.0)
    def sometimes_fails():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("try again")
        return "ok"

    assert sometimes_fails() == "ok"
    assert attempts["count"] == 3  # 2 fallos + 1 éxito
    assert sleep_calls == [0.1, 0.2]  # backoff exponencial respetado


def test_retry_with_backoff_raises_after_max(monkeypatch):
    sleep_calls = []
    errors = []

    def fake_sleep(t):
        sleep_calls.append(t)

    def fake_warning(msg):
        errors.append(msg)

    def fake_error(msg):
        errors.append(msg)

    monkeypatch.setattr(utils, "time", types.SimpleNamespace(sleep=fake_sleep))
    monkeypatch.setattr(utils.logger, "warning", lambda *a, **k: fake_warning(a[0]))
    monkeypatch.setattr(utils.logger, "error", lambda *a, **k: fake_error(a[0]))

    @utils.retry_with_backoff(max_retries=1, base_delay=0.05, max_delay=1.0)
    def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        always_fail()

    assert sleep_calls == [0.05]
    assert any("Intento 1/1" in msg for msg in errors)
    assert any("Todos los intentos fallaron" in msg for msg in errors)


def test_batch_process_handles_batches_and_errors(monkeypatch):
    captured = []
    monkeypatch.setattr(utils.logger, "error", lambda *a, **k: captured.append(a[0]))

    def processor(batch):
        if batch == [3, 4]:
            raise ValueError("fail")
        return [x * 2 for x in batch]

    result = utils.batch_process([1, 2, 3, 4], batch_size=2, processor=processor)

    assert result == [[2, 4], None]
    assert any("Error procesando lote" in msg for msg in captured)


def test_format_cop_and_truncate_string():
    assert utils.format_cop(1234567) == "$1.234.567"
    assert utils.format_cop(1000.51) == "$1.001"
    assert utils.format_cop("invalid") == "$0"

    assert utils.truncate_string("abc", max_length=5) == "abc"
    assert utils.truncate_string("abcdef", max_length=5) == "ab..."


def test_utc_now_and_to_bogota():
    now_value = utils.utc_now()
    assert now_value.tzinfo is not None

    localized = utils.to_bogota(now_value)
    assert localized.tzinfo is not None
    # Asegura que devuelve mismo objeto si None
    assert utils.to_bogota(None) is None
