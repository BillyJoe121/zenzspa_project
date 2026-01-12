from rest_framework import serializers

from .models import NotificationPreference


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "email_enabled",
            "sms_enabled",
            "push_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
            "timezone",
        ]
