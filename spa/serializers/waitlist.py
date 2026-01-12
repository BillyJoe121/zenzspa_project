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

    def validate(self, attrs):
        service_ids = attrs.get("service_ids") or []
        if not service_ids:
            return attrs
        from spa.models import Service

        services = list(
            Service.objects.filter(id__in=service_ids, is_active=True).values_list("id", flat=True)
        )
        missing = set(service_ids) - set(services)
        if missing:
            raise serializers.ValidationError(
                {"service_ids": "Uno o más servicios no existen o están inactivos."}
            )
        return attrs


class WaitlistConfirmSerializer(serializers.Serializer):
    accept = serializers.BooleanField(default=True)
