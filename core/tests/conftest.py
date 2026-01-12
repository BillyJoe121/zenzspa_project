import pytest
from rest_framework.test import APIRequestFactory


@pytest.fixture
def api_rf():
    """Factory para crear requests DRF en tests."""
    return APIRequestFactory()


@pytest.fixture
def admin_user(django_user_model):
    """Usuario con rol ADMIN."""
    return django_user_model.objects.create_user(
        phone_number="+573157589548",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        role="ADMIN",
        is_active=True,
        is_verified=True,
        password="pass1234",
    )


@pytest.fixture
def client_user(django_user_model):
    """Usuario con rol CLIENT."""
    return django_user_model.objects.create_user(
        phone_number="+573007654321",
        email="client@example.com",
        first_name="Client",
        last_name="User",
        role="CLIENT",
        is_active=True,
        is_verified=True,
        password="pass1234",
    )
