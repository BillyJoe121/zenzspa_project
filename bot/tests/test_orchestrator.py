import pytest
from bot.services import PromptOrchestrator

@pytest.mark.django_db
def test_prompt_construction(user, bot_config):
    """Verifica que el prompt final contenga el mensaje del usuario y contexto."""
    orchestrator = PromptOrchestrator()
    user_message = "Quiero un masaje relajante"

    full_prompt, is_valid = orchestrator.build_full_prompt(user, user_message)

    # Verificaciones clave
    assert is_valid is True
    assert user_message in full_prompt
    assert bot_config.booking_url in full_prompt
    assert "[INICIO_MENSAJE_USUARIO]" in full_prompt
    assert "REGLA DE SEGURIDAD SUPREMA" in full_prompt

@pytest.mark.django_db
def test_prompt_missing_config(user):
    """Si no hay configuración, debe devolver tupla con is_valid=False."""
    # No creamos bot_config fixture aquí
    orchestrator = PromptOrchestrator()
    prompt, is_valid = orchestrator.build_full_prompt(user, "Hola")

    assert is_valid is False
    assert prompt == ""