import pytest
from bot.services import is_trivial_message, PromptOrchestrator


@pytest.mark.django_db
class TestTrivialMessageDetection:
    """Tests para detección de mensajes triviales (Mejora #9)"""

    def test_detect_greetings(self):
        """Debe detectar saludos como triviales"""
        greetings = [
            "hola",
            "Hola!",
            "HOLA",
            "buenos días",
            "Buenas tardes",
            "hey",
            "hi",
            "hello",
        ]

        for greeting in greetings:
            assert is_trivial_message(greeting) is True, f"Falló al detectar: {greeting}"

    def test_detect_thanks(self):
        """Debe detectar agradecimientos como triviales"""
        thanks = [
            "gracias",
            "Muchas gracias!",
            "ok",
            "OK",
            "vale",
            "perfecto",
            "excelente",
        ]

        for thank in thanks:
            assert is_trivial_message(thank) is True, f"Falló al detectar: {thank}"

    def test_detect_farewells(self):
        """Debe detectar despedidas como triviales"""
        farewells = [
            "adiós",
            "chao",
            "Hasta luego!",
            "nos vemos",
            "bye",
        ]

        for farewell in farewells:
            assert is_trivial_message(farewell) is True, f"Falló al detectar: {farewell}"

    def test_detect_emojis(self):
        """Debe detectar emojis comunes como triviales"""
        emojis = [
            "👋",
            "👍",
            "😊",
            "🙏",
        ]

        for emoji in emojis:
            assert is_trivial_message(emoji) is True, f"Falló al detectar: {emoji}"

    def test_non_trivial_messages(self):
        """No debe detectar mensajes complejos como triviales"""
        complex_messages = [
            "¿Qué servicios tienen?",
            "Quiero agendar una cita",
            "Cuál es el precio del masaje?",
            "hola, quiero información sobre los paquetes",  # Tiene más que solo saludo
            "gracias por la información anterior",  # Tiene contexto adicional
        ]

        for msg in complex_messages:
            assert is_trivial_message(msg) is False, f"Detectó incorrectamente como trivial: {msg}"

    def test_trivial_prompt_has_no_services_context(self, user, bot_config):
        """El prompt trivial no debe incluir contexto de servicios/productos"""
        orchestrator = PromptOrchestrator()

        # Mensaje trivial
        prompt_trivial, is_valid = orchestrator.build_full_prompt(user, "Hola")

        # Verificaciones
        assert is_valid is True
        assert len(prompt_trivial) < 500  # Prompt trivial debe ser mucho más corto
        assert "servicios" not in prompt_trivial.lower() or "Eres un asistente" in prompt_trivial  # No debe tener lista de servicios
        assert bot_config.site_name in prompt_trivial

    def test_complex_prompt_has_services_context(self, user, bot_config):
        """El prompt completo debe incluir contexto de servicios"""
        orchestrator = PromptOrchestrator()

        # Mensaje complejo
        prompt_complex, is_valid = orchestrator.build_full_prompt(user, "¿Qué servicios tienen?")

        # Verificaciones
        assert is_valid is True
        assert len(prompt_complex) > 500  # Prompt completo debe ser más largo
        # Debe tener delimitadores y contexto
        assert "[INICIO_MENSAJE_USUARIO]" in prompt_complex
        assert "REGLA DE SEGURIDAD SUPREMA" in prompt_complex

    def test_whitespace_handling(self):
        """Debe manejar espacios en blanco correctamente"""
        assert is_trivial_message("  hola  ") is True
        assert is_trivial_message("hola\n") is True
        assert is_trivial_message("\t\tgracias\t\t") is True

    def test_case_insensitive(self):
        """Debe ser case-insensitive"""
        assert is_trivial_message("HOLA") is True
        assert is_trivial_message("Hola") is True
        assert is_trivial_message("hola") is True
        assert is_trivial_message("GrAcIaS") is True
