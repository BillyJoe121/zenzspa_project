from types import SimpleNamespace

import pytest
from rest_framework import serializers

from core import serializers as core_serializers
from core.models import AdminNotification


class NotificationSerializer(core_serializers.DynamicFieldsModelSerializer):
    class Meta:
        model = AdminNotification
        fields = ["id", "title", "message", "is_read", "subtype"]
        role_based_fields = {"ADMIN": ["is_read"], "STAFF": ["subtype"]}


class MaskingSerializer(core_serializers.DataMaskingMixin, serializers.ModelSerializer):
    class Meta:
        model = AdminNotification
        fields = ["title", "message"]
        mask_fields = {
            "message": {"mask_with": "default", "visible_for": ["ADMIN"]},
            "title": {"mask_with": "email", "visible_for": ["STAFF"]},
        }


class ReadOnlyNotificationSerializer(core_serializers.ReadOnlyModelSerializer):
    class Meta:
        model = AdminNotification
        fields = ["id", "title", "message", "is_read"]


@pytest.mark.django_db
def test_dynamic_fields_respects_role_and_includes():
    notif = AdminNotification.objects.create(title="T", message="M")
    request = SimpleNamespace(user=SimpleNamespace(role="CLIENT"))
    serializer = NotificationSerializer(notif, context={"request": request})
    assert set(serializer.data.keys()) == {"id", "title", "message"}

    serializer = NotificationSerializer(
        notif,
        context={"request": request, "include_fields": ["id", "title"]},
    )
    assert set(serializer.data.keys()) == {"id", "title"}

    serializer = NotificationSerializer(
        notif,
        context={"request": request, "exclude_fields": ["message"]},
    )
    assert "message" not in serializer.data


@pytest.mark.django_db
def test_data_masking_mixin_masks_based_on_role():
    notif = AdminNotification.objects.create(title="user@example.com", message="secret")

    client_request = SimpleNamespace(user=SimpleNamespace(role="CLIENT"))
    client_data = MaskingSerializer(notif, context={"request": client_request}).data
    assert client_data["message"] == "***"
    assert client_data["title"].startswith("u***")

    admin_request = SimpleNamespace(user=SimpleNamespace(role="ADMIN"))
    admin_data = MaskingSerializer(notif, context={"request": admin_request}).data
    assert admin_data["message"] == "secret"  # no masking for ADMIN


@pytest.mark.django_db
def test_read_only_serializer_marks_fields():
    notif = AdminNotification.objects.create(title="T", message="M")
    serializer = ReadOnlyNotificationSerializer(notif)
    assert all(field.read_only for field in serializer.fields.values())
