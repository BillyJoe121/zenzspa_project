from rest_framework import serializers

from ..models import AppointmentItem, Service, ServiceCategory, ServiceMedia
from .appointment_common import ServiceSummarySerializer


class ServiceCategorySerializer(serializers.ModelSerializer):
    service_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ["id", "name", "description", "is_low_supervision", "service_count"]
        read_only_fields = ["service_count"]

    def get_service_count(self, obj):
        return obj.services.filter(is_active=True, deleted_at__isnull=True).count()


class ServiceMediaSerializer(serializers.ModelSerializer):
    """Serializer para medios de servicios (imágenes/videos)."""

    media_type_display = serializers.CharField(source="get_media_type_display", read_only=True)

    class Meta:
        model = ServiceMedia
        fields = [
            "id",
            "service",
            "media_url",
            "media_type",
            "media_type_display",
            "alt_text",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    media = ServiceMediaSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "description",
            "duration",
            "price",
            "vip_price",
            "category",
            "category_name",
            "is_active",
            "what_is_included",
            "benefits",
            "contraindications",
            "main_media_url",
            "is_main_media_video",
            "media",
        ]


class AppointmentItemSerializer(serializers.ModelSerializer):
    service = ServiceSummarySerializer(read_only=True)

    class Meta:
        model = AppointmentItem
        fields = ["id", "service", "duration", "price_at_purchase"]
