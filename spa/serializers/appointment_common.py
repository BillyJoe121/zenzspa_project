from django.contrib.auth import get_user_model
from rest_framework import serializers

from ..models import Service

CustomUser = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "first_name", "last_name", "phone_number"]


class ServiceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "duration"]
