import pytest
from django.core.cache import cache
from model_bakery import baker
from bot.models import BotConfiguration
from rest_framework.test import APIClient

@pytest.fixture(autouse=True)
def clear_cache():
    """Limpia la caché de Redis antes y después de cada test."""
    cache.clear()
    yield
    cache.clear()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user():
    """Crea un usuario estándar."""
    return baker.make('users.CustomUser', phone_number='+573157589548')

@pytest.fixture
def bot_config():
    """Crea una configuración base válida."""
    return BotConfiguration.objects.create(
        site_name="Spa Test",
        booking_url="https://test.com",
        admin_phone="+573157589548",
        system_prompt_template=(
            "Eres un bot. Contexto: {{user_message}}. "
            "Servicios: {{services_context}}. "
            "Productos: {{products_context}}. "
            "Agenda aquí: {{booking_url}}. "
            "Admin: {{admin_phone}}."
        )
    )