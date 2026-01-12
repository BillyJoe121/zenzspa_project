import pytest

from core.models import (
    AdminNotification,
    AuditLog,
    GlobalSettings,
    IdempotencyKey,
)
from django.utils import timezone
from spa.models import ServiceCategory


@pytest.mark.django_db
def test_soft_delete_and_restore():
    category = ServiceCategory.objects.create(name="Masajes", description="desc")
    pk = category.pk

    category.delete()
    assert ServiceCategory.objects.filter(pk=pk).exists() is False
    deleted = ServiceCategory.all_objects.get(pk=pk)
    assert deleted.is_deleted is True
    assert deleted.deleted_at is not None

    deleted.restore()
    restored = ServiceCategory.objects.get(pk=pk)
    assert restored.is_deleted is False
    assert restored.deleted_at is None

    restored.hard_delete()
    assert ServiceCategory.all_objects.filter(pk=pk).exists() is False


@pytest.mark.django_db
def test_idempotency_key_mark_processing_updates_fields():
    key = IdempotencyKey.objects.create(
        key="key-processing-123456",
        endpoint="/api/test/",
        status=IdempotencyKey.Status.COMPLETED,
        locked_at=None,
    )
    key.mark_processing()
    key.refresh_from_db()
    assert key.status == IdempotencyKey.Status.PENDING
    assert key.locked_at is not None


@pytest.mark.django_db
def test_audit_log_str_uses_display(admin_user):
    log = AuditLog.objects.create(
        action=AuditLog.Action.APPOINTMENT_COMPLETED,
        admin_user=admin_user,
        target_user=None,
        details="done",
    )
    rendered = str(log)
    assert "Cita completada" in rendered
    assert admin_user.phone_number in rendered


@pytest.mark.django_db
def test_global_settings_extra_validations():
    settings_obj = GlobalSettings.load()
    settings_obj.appointment_buffer_time = 500
    settings_obj.advance_expiration_minutes = 0
    settings_obj.credit_expiration_days = 0
    settings_obj.return_window_days = -1
    settings_obj.loyalty_months_required = 0
    settings_obj.waitlist_ttl_minutes = 1
    settings_obj.developer_payout_threshold = 0

    with pytest.raises(Exception) as exc:
        settings_obj.clean()
    message = str(exc.value)
    for field in [
        "appointment_buffer_time",
        "advance_expiration_minutes",
        "credit_expiration_days",
        "return_window_days",
        "loyalty_months_required",
        "waitlist_ttl_minutes",
        "developer_payout_threshold",
    ]:
        assert field in message


@pytest.mark.django_db
def test_admin_notification_str_includes_title():
    notif = AdminNotification.objects.create(
        title="Alerta",
        message="Mensaje",
        notification_type=AdminNotification.NotificationType.USUARIOS,
        subtype=AdminNotification.NotificationSubtype.OTRO,
    )
    assert "Alerta" in str(notif)


@pytest.mark.django_db
def test_soft_delete_queryset_updates_timestamps_and_flags():
    first = ServiceCategory.objects.create(name="Masajes", description="desc")
    second = ServiceCategory.objects.create(name="Spa", description="desc")
    before_update = first.updated_at

    deleted_count = ServiceCategory.objects.filter(pk__in=[first.pk, second.pk]).delete()
    assert deleted_count == 2

    refreshed_first = ServiceCategory.all_objects.get(pk=first.pk)
    refreshed_second = ServiceCategory.all_objects.get(pk=second.pk)

    assert refreshed_first.is_deleted is True
    assert refreshed_second.is_deleted is True
    assert refreshed_first.deleted_at is not None
    assert refreshed_second.deleted_at is not None
    assert refreshed_first.updated_at >= before_update
    assert refreshed_second.updated_at >= before_update


@pytest.mark.django_db
def test_soft_delete_concurrent_deletes_is_idempotent():
    """
    Validar fix para CORE-SOFTDELETE-RACE: deletes concurrentes
    no deben causar DoesNotExist, deben ser idempotentes.
    """
    category = ServiceCategory.objects.create(name="Test Concurrent", description="desc")
    pk = category.pk

    # Primer delete debe marcar como eliminado
    category.delete()
    assert ServiceCategory.all_objects.get(pk=pk).is_deleted is True

    # Segundo delete sobre la misma instancia (ya marcada como eliminada)
    # NO debe lanzar excepción, debe salir silenciosamente
    category.delete()  # No debe lanzar DoesNotExist

    # Obtener instancia ya eliminada y volver a intentar delete
    already_deleted = ServiceCategory.all_objects.get(pk=pk)
    already_deleted.delete()  # Tampoco debe lanzar excepción

    # Verificar que sigue eliminado
    final = ServiceCategory.all_objects.get(pk=pk)
    assert final.is_deleted is True


@pytest.mark.django_db
def test_soft_delete_already_deleted_instance_does_not_fail():
    """
    Validar que llamar delete() en una instancia que ya tiene
    is_deleted=True no causa errores.
    """
    category = ServiceCategory.objects.create(name="Already Deleted", description="desc")
    pk = category.pk

    # Marcar como eliminado
    category.delete()

    # Refrescar desde all_objects
    deleted_instance = ServiceCategory.all_objects.get(pk=pk)
    assert deleted_instance.is_deleted is True

    # Intentar delete nuevamente sobre la instancia eliminada
    deleted_instance.delete()  # Debe salir por el if self.is_deleted

    # Verificar que sigue eliminado (sin cambios)
    assert ServiceCategory.all_objects.get(pk=pk).is_deleted is True
