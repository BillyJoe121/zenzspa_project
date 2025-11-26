import os
import runpy
from pathlib import Path

import pytest

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.py"

TRACKED_ENV_KEYS = {
    "SECRET_KEY",
    "DB_PASSWORD",
    "DEBUG",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_VERIFY_SERVICE_SID",
    "WOMPI_PUBLIC_KEY",
    "WOMPI_INTEGRITY_SECRET",
    "WOMPI_INTEGRITY_KEY",
    "WOMPI_EVENT_SECRET",
    "GEMINI_API_KEY",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "CORS_ALLOWED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS",
    "BOT_GEMINI_TIMEOUT",
    "AXES_ENABLED",
    "AXES_FAILURE_LIMIT",
    "AXES_COOLOFF_TIME_MIN",
    "AXES_ONLY_USER_FAILURES",
    "AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP",
}


def _debug_env(**overrides):
    env = {
        "SECRET_KEY": "test-secret-12345678901234567890",
        "DB_PASSWORD": "db-pass",
        "DEBUG": "1",
        "REDIS_URL": "redis://127.0.0.1:6379/1",
        "CELERY_BROKER_URL": "redis://127.0.0.1:6379/0",
        "EMAIL_HOST_USER": "user@example.com",
        "EMAIL_HOST_PASSWORD": "pass1234",
        "GEMINI_API_KEY": "demo-key",
        "FERNET_KEY": "test-fernet-key-32-bytes-long-1234567890ab=",
    }
    env.update(overrides)
    return env


def _prod_env(**overrides):
    env = _debug_env(
        DEBUG="0",
        TWILIO_ACCOUNT_SID="ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_VERIFY_SERVICE_SID="VAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        WOMPI_PUBLIC_KEY="pub-key",
        WOMPI_INTEGRITY_SECRET="integrity",
        WOMPI_INTEGRITY_KEY="integrity",
        WOMPI_EVENT_SECRET="event-secret",
        GEMINI_API_KEY="gemini-123",
        CORS_ALLOWED_ORIGINS="https://app.zenzspa.com",
        CSRF_TRUSTED_ORIGINS="https://app.zenzspa.com",
        ALLOWED_HOSTS="app.zenzspa.com",
        REDIS_URL="rediss://127.0.0.1:6379/1",
        CELERY_BROKER_URL="rediss://127.0.0.1:6379/0",
        SITE_URL="https://app.zenzspa.com",
        DEFAULT_FROM_EMAIL="noreply@zenzspa.com",
        WOMPI_REDIRECT_URL="https://app.zenzspa.com/payment-result",
    )
    env.update(overrides)
    return env


def _run_settings(monkeypatch, env):
    tracked = TRACKED_ENV_KEYS | set(env.keys())
    for key in tracked:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(SETTINGS_FILE))


def _set_env(monkeypatch, env):
    tracked = TRACKED_ENV_KEYS | set(env.keys())
    for key in tracked:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


@pytest.mark.django_db(False)
def test_validate_required_env_vars_detects_missing_secret(monkeypatch):
    from zenzspa import settings

    _set_env(monkeypatch, {"DEBUG": "1", "DB_PASSWORD": "pwd"})
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError) as exc:
        settings.validate_required_env_vars()
    assert "SECRET_KEY" in str(exc.value)


@pytest.mark.django_db(False)
def test_validate_required_env_vars_requires_twilio_on_prod(monkeypatch):
    from zenzspa import settings

    env = _prod_env()
    env.pop("TWILIO_ACCOUNT_SID")
    _set_env(monkeypatch, env)

    with pytest.raises(RuntimeError) as exc:
        settings.validate_required_env_vars()
    assert "TWILIO_ACCOUNT_SID" in str(exc.value)


@pytest.mark.django_db(False)
def test_validate_required_env_vars_passes_with_all_required(monkeypatch):
    from zenzspa import settings

    env = _prod_env()
    _set_env(monkeypatch, env)

    # Should not raise
    settings.validate_required_env_vars()


def test_settings_production_requires_cors_origins(monkeypatch):
    env = _prod_env()
    env.pop("CORS_ALLOWED_ORIGINS")

    with pytest.raises(RuntimeError) as exc:
        _run_settings(monkeypatch, env)
    assert "CORS_ALLOWED_ORIGINS" in str(exc.value)


def test_settings_production_rejects_localhost(monkeypatch):
    """Test que localhost es rechazado en CORS_ALLOWED_ORIGINS en producción"""
    env = _prod_env(CORS_ALLOWED_ORIGINS="https://app.zenzspa.com http://localhost:3000")

    with pytest.raises(RuntimeError) as exc:
        _run_settings(monkeypatch, env)
    assert "localhost" in str(exc.value).lower()


def test_settings_production_rejects_localhost_in_allowed_hosts(monkeypatch):
    """Test que localhost es rechazado en ALLOWED_HOSTS en producción"""
    env = _prod_env(ALLOWED_HOSTS="app.zenzspa.com localhost")

    with pytest.raises(RuntimeError) as exc:
        _run_settings(monkeypatch, env)
    assert "localhost" in str(exc.value).lower() or "host" in str(exc.value).lower()



def test_axes_configuration_enabled(monkeypatch):
    env = _prod_env(
        AXES_ENABLED="1",
        AXES_FAILURE_LIMIT="7",
        AXES_COOLOFF_TIME_MIN="30",
    )
    module = _run_settings(monkeypatch, env)

    assert module["AXES_ENABLED"] is True
    assert module["AXES_FAILURE_LIMIT"] == 7
    assert module["AXES_COOLOFF_TIME"] == 30
    assert module["AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP"] is True


def test_bot_timeout_defaults_when_invalid(monkeypatch):
    env = _debug_env(BOT_GEMINI_TIMEOUT="not-a-number")
    module = _run_settings(monkeypatch, env)

    assert module["BOT_GEMINI_TIMEOUT"] == 20


def test_rest_framework_renderers_toggle_by_debug(monkeypatch):
    debug_module = _run_settings(monkeypatch, _debug_env())
    prod_module = _run_settings(monkeypatch, _prod_env())

    assert "rest_framework.renderers.BrowsableAPIRenderer" in debug_module["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"]
    assert prod_module["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"] == ("rest_framework.renderers.JSONRenderer",)


def test_cors_allow_credentials_defaults_false_on_prod(monkeypatch):
    module = _run_settings(monkeypatch, _prod_env())
    assert module["CORS_ALLOW_CREDENTIALS"] is False

    module_true = _run_settings(monkeypatch, _prod_env(CORS_ALLOW_CREDENTIALS="1"))
    assert module_true["CORS_ALLOW_CREDENTIALS"] is True


def test_secret_key_fallbacks_parsed(monkeypatch):
    env = _debug_env(SECRET_KEY_FALLBACKS="fallback1 fallback2")
    module = _run_settings(monkeypatch, env)
    assert module["SECRET_KEY_FALLBACKS"] == ["fallback1", "fallback2"]


def test_celery_beat_schedule_filename_has_default(monkeypatch):
    module = _run_settings(monkeypatch, _debug_env())
    assert module["CELERY_BEAT_SCHEDULE_FILENAME"].endswith("celerybeat-schedule")
