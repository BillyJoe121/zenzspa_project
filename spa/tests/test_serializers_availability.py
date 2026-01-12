import pytest

from spa.serializers import AvailabilityCheckSerializer


def test_availability_serializer_coerces_single_service():
    data = {"service_id": "123e4567-e89b-12d3-a456-426614174000", "date": "2025-01-01"}
    serializer = AvailabilityCheckSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert str(serializer.validated_data["service_ids"][0]) == data["service_id"]


def test_availability_serializer_requires_services():
    serializer = AvailabilityCheckSerializer(data={"date": "2025-01-01"})
    assert not serializer.is_valid()
    assert "service_ids" in serializer.errors
