from core.tasks import send_transactional_email
from core.tasks import cleanup_old_idempotency_keys
from core.models import IdempotencyKey
from django.utils import timezone
from datetime import timedelta
import pytest


def test_send_transactional_email_returns_payload():
    result = send_transactional_email(
        template_key="welcome",
        to_email="user@example.com",
        context={"name": "User"},
    )
    assert result["template_key"] == "welcome"
    assert result["to"] == "user@example.com"
    assert "sent_at" in result


@pytest.mark.django_db
def test_cleanup_old_idempotency_keys_deletes_completed_and_stale():
    old_completed = IdempotencyKey.objects.create(
        key="completed-old-123456",
        endpoint="/api/test/",
        status=IdempotencyKey.Status.COMPLETED,
        completed_at=timezone.now() - timedelta(days=8),
    )
    recent_completed = IdempotencyKey.objects.create(
        key="completed-new-123456",
        endpoint="/api/test/",
        status=IdempotencyKey.Status.COMPLETED,
        completed_at=timezone.now() - timedelta(days=1),
    )
    stale_pending = IdempotencyKey.objects.create(
        key="pending-stale-123456",
        endpoint="/api/test/",
        status=IdempotencyKey.Status.PENDING,
        locked_at=timezone.now() - timedelta(hours=25),
    )
    fresh_pending = IdempotencyKey.objects.create(
        key="pending-fresh-123456",
        endpoint="/api/test/",
        status=IdempotencyKey.Status.PENDING,
        locked_at=timezone.now(),
    )

    result = cleanup_old_idempotency_keys()

    assert result["deleted_completed"] >= 1
    assert result["deleted_stale"] >= 1
    assert not IdempotencyKey.objects.filter(pk=old_completed.pk).exists()
    assert IdempotencyKey.objects.filter(pk=recent_completed.pk).exists()
    assert not IdempotencyKey.objects.filter(pk=stale_pending.pk).exists()
    assert IdempotencyKey.objects.filter(pk=fresh_pending.pk).exists()
