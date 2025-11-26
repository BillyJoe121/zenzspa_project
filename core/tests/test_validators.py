import io
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from rest_framework import serializers
from django.utils import timezone
from PIL import Image

from core import validators


def test_percentage_validator_accepts_range():
    validators.percentage_0_100(0)
    validators.percentage_0_100(100)
    with pytest.raises(serializers.ValidationError):
        validators.percentage_0_100(150)


def test_validate_colombian_phone():
    validators.validate_colombian_phone("+571231231231")
    with pytest.raises(ValidationError):
        validators.validate_colombian_phone("3001231231")


def test_validate_positive_amount():
    validators.validate_positive_amount(1)
    with pytest.raises(ValidationError):
        validators.validate_positive_amount(-1)
    with pytest.raises(ValidationError):
        validators.validate_positive_amount(0)
    validators.validate_positive_amount(None)


def test_validate_future_date():
    future = timezone.now().date() + timedelta(days=1)
    validators.validate_future_date(future)
    with pytest.raises(ValidationError):
        validators.validate_future_date(timezone.now().date())


def test_validate_date_range():
    start = date(2024, 1, 1)
    end = date(2024, 1, 2)
    validators.validate_date_range(start, end)
    with pytest.raises(ValidationError):
        validators.validate_date_range(end, start)


def test_validate_uuid_format():
    validators.validate_uuid_format("00000000-0000-0000-0000-000000000000")
    with pytest.raises(ValidationError):
        validators.validate_uuid_format("not-a-uuid")


def test_validate_min_age():
    today = timezone.now().date()
    adult = today - timedelta(days=25 * 365)
    minor = today - timedelta(days=10 * 365)
    validators.validate_min_age(adult, min_age=18)
    with pytest.raises(ValidationError):
        validators.validate_min_age(minor, min_age=18)


def test_validate_file_size_and_dimensions():
    too_large = SimpleNamespace(size=6 * 1024 * 1024)
    with pytest.raises(ValidationError):
        validators.validate_file_size(too_large, max_size_mb=5)

    small_image_bytes = io.BytesIO()
    Image.new("RGB", (10, 10)).save(small_image_bytes, format="PNG")
    small_image_bytes.seek(0)
    validators.validate_image_dimensions(small_image_bytes, max_width=100, max_height=100)

    big_image_bytes = io.BytesIO()
    Image.new("RGB", (5000, 5000)).save(big_image_bytes, format="PNG")
    big_image_bytes.seek(0)
    with pytest.raises(ValidationError):
        validators.validate_image_dimensions(big_image_bytes, max_width=100, max_height=100)
