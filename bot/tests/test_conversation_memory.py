import pytest
from django.core.cache import cache
from bot.services import ConversationMemoryService


@pytest.mark.django_db
class TestConversationMemory:
    """Tests para la memoria conversacional (Mejora #10)"""

    def setup_method(self):
        """Limpiar caché antes de cada test"""
        cache.clear()

    def test_add_and_get_history(self, user):
        """Debe agregar y recuperar historial de conversación"""
        # Verificar historial vacío inicialmente
        history = ConversationMemoryService.get_conversation_history(user.id)
        assert history == []

        # Agregar primer mensaje
        ConversationMemoryService.add_to_history(
            user.id, "Hola", "Hola! ¿En qué puedo ayudarte?"
        )

        # Verificar que se agregó
        history = ConversationMemoryService.get_conversation_history(user.id)
        assert len(history) == 2  # user + assistant
        assert history[0]['role'] == 'user'
        assert history[0]['content'] == "Hola"
        assert history[1]['role'] == 'assistant'
        assert history[1]['content'] == "Hola! ¿En qué puedo ayudarte?"

    def test_window_size_limit(self, user):
        """Debe mantener solo los últimos 6 mensajes (3 pares)"""
        # Agregar 5 pares de mensajes (10 mensajes totales)
        for i in range(5):
            ConversationMemoryService.add_to_history(
                user.id, f"Pregunta {i}", f"Respuesta {i}"
            )

        history = ConversationMemoryService.get_conversation_history(user.id)

        # Debe mantener solo los últimos 6 mensajes (3 pares)
        assert len(history) == 6

        # Verificar que son los últimos 3 pares (índices 2, 3, 4)
        assert history[0]['content'] == "Pregunta 2"
        assert history[1]['content'] == "Respuesta 2"
        assert history[2]['content'] == "Pregunta 3"
        assert history[3]['content'] == "Respuesta 3"
        assert history[4]['content'] == "Pregunta 4"
        assert history[5]['content'] == "Respuesta 4"

    def test_clear_history(self, user):
        """Debe limpiar el historial correctamente"""
        # Agregar mensajes
        ConversationMemoryService.add_to_history(
            user.id, "Test", "Response"
        )

        # Verificar que existe
        history = ConversationMemoryService.get_conversation_history(user.id)
        assert len(history) == 2

        # Limpiar
        ConversationMemoryService.clear_history(user.id)

        # Verificar que está vacío
        history = ConversationMemoryService.get_conversation_history(user.id)
        assert history == []

    def test_separate_user_histories(self, user):
        """Cada usuario debe tener su propio historial independiente"""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Crear segundo usuario
        user2 = User.objects.create(
            first_name="User2",
            phone_number="+573000000099",
            email="user2@test.com"
        )

        # Agregar mensajes para user1
        ConversationMemoryService.add_to_history(
            user.id, "User1 message", "User1 response"
        )

        # Agregar mensajes para user2
        ConversationMemoryService.add_to_history(
            user2.id, "User2 message", "User2 response"
        )

        # Verificar que son independientes
        history1 = ConversationMemoryService.get_conversation_history(user.id)
        history2 = ConversationMemoryService.get_conversation_history(user2.id)

        assert len(history1) == 2
        assert len(history2) == 2
        assert history1[0]['content'] == "User1 message"
        assert history2[0]['content'] == "User2 message"

    def test_timestamps_added(self, user):
        """Cada mensaje debe tener timestamp"""
        import time

        before_time = time.time()
        ConversationMemoryService.add_to_history(
            user.id, "Test", "Response"
        )
        after_time = time.time()

        history = ConversationMemoryService.get_conversation_history(user.id)

        # Verificar que tienen timestamps
        for msg in history:
            assert 'timestamp' in msg
            assert before_time <= msg['timestamp'] <= after_time
