from rest_framework import serializers
from django.utils import timezone


class WaitlistJoinSerializer(serializers.Serializer):
    desired_date = serializers.DateField()
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_desired_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("La fecha deseada debe ser futura.")
        return value


class WaitlistConfirmSerializer(serializers.Serializer):
    accept = serializers.BooleanField(default=True)

