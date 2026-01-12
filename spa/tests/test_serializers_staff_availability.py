import pytest
from datetime import time
from django.test import RequestFactory
from model_bakery import baker

from spa.serializers import StaffAvailabilitySerializer


@pytest.mark.django_db
def test_staff_availability_validates_time_order():
    factory = RequestFactory()
    request = factory.get('/')
    user = baker.make("users.CustomUser", role="STAFF")
    data = {
        "staff_member_id": user.id,
        "day_of_week": 1,
        "start_time": time(10, 0),
        "end_time": time(9, 0),
    }
    serializer = StaffAvailabilitySerializer(data=data, context={"request": request})
    assert not serializer.is_valid()
    assert "non_field_errors" in serializer.errors or "start_time" in serializer.errors


@pytest.mark.django_db
def test_staff_availability_valid():
    factory = RequestFactory()
    request = factory.get('/')
    admin_user = baker.make("users.CustomUser", role="STAFF", is_staff=True)
    request.user = admin_user
    user = baker.make("users.CustomUser", role="STAFF")
    data = {
        "staff_member_id": user.id,
        "day_of_week": 1,
        "start_time": time(9, 0),
        "end_time": time(18, 0),
    }
    serializer = StaffAvailabilitySerializer(data=data, context={"request": request})
    assert serializer.is_valid(), serializer.errors
