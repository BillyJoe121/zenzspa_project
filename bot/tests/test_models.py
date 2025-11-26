import pytest
from django.core.exceptions import ValidationError
from django.core.cache import cache
from bot.models import BotConfiguration

@pytest.mark.django_db
class TestBotConfigurationModels:
    
    def test_validation_clean_happy_path(self):
        """Una configuración válida no debe levantar errores."""
        # CORRECCIÓN: Usamos {{variable}} SIN espacios para coincidir con models.py
        valid_template = (
            "Hola {{user_message}}. "
            "Servicios: {{services_context}}. "
            "Productos: {{products_context}}. "
            "Agenda en: {{booking_url}}. "
            "Admin: {{admin_phone}}."
        )
        config = BotConfiguration(
            booking_url="https://valid.com",
            admin_phone="+57 300 123 4567",
            system_prompt_template=valid_template
        )
        config.clean()

    def test_validation_invalid_url(self):
        config = BotConfiguration(booking_url="bad-url")
        with pytest.raises(ValidationError) as exc:
            config.clean()
        assert 'booking_url' in exc.value.message_dict

    def test_validation_invalid_phone(self):
        config = BotConfiguration(admin_phone="3001234567") 
        with pytest.raises(ValidationError) as exc:
            config.clean()
        assert 'admin_phone' in exc.value.message_dict

    def test_validation_missing_variables_in_prompt(self):
        config = BotConfiguration(
            system_prompt_template="Hola soy un bot sin variables."
        )
        with pytest.raises(ValidationError) as exc:
            config.clean()
        
        errors = exc.value.message_dict
        assert 'system_prompt_template' in errors
        # CORRECCIÓN: Busamos '{{user_message}}' sin espacios
        assert '{{user_message}}' in errors['system_prompt_template'][0]

    def test_cache_invalidation_on_save(self):
        cache.set('bot_config_version', 1)
        # Usamos template válido mínimo
        BotConfiguration.objects.create(
            site_name="Test",
            booking_url="https://test.com",
            admin_phone="+573001234567",
            system_prompt_template="{{user_message}} {{services_context}} {{products_context}} {{booking_url}} {{admin_phone}}"
        )
        assert cache.get('bot_config_version') == 2