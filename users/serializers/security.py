from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from ..models import CustomUser, UserSession


class VerifySMSSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)
    recaptcha_token = serializers.CharField(required=False, allow_blank=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value, is_active=True).exists():
            raise serializers.ValidationError(
                "No existe una cuenta activa con este número de teléfono."
            )
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])


class FlagNonGrataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["internal_notes", "internal_photo_url"]


class StaffListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",
            "is_active",
            "is_verified",
        ]


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            "id",
            "ip_address",
            "user_agent",
            "last_activity",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields
