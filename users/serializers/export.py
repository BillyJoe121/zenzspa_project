from rest_framework import serializers

from ..models import CustomUser


class UserExportSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_verified",
            "email_verified",
            "status",
            "created_at",
            "last_login",
        ]

    def get_status(self, obj):
        if obj.is_persona_non_grata:
            return "CNG"
        if not obj.is_active:
            return "Inactivo"
        return "Activo"
