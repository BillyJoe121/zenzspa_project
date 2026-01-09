import time

from django.core.cache import cache


class ConversationMemoryService:
    """
    Gestiona el historial de conversación para contexto.
    """

    WINDOW_SIZE = 40  # Aumentado a 40 (aprox 20 pares de preguntas/respuestas)
    CACHE_TIMEOUT = 3600  # 1 hora

    @staticmethod
    def get_conversation_history(user_id: int) -> list[dict]:
        cache_key = f"bot:conversation:{user_id}"
        return cache.get(cache_key, [])

    @staticmethod
    def add_to_history(user_id: int, message: str, response: str):
        cache_key = f"bot:conversation:{user_id}"
        history = ConversationMemoryService.get_conversation_history(user_id)

        history.append(
            {
                "role": "user",
                "content": message,
                "timestamp": time.time(),
            }
        )

        history.append(
            {
                "role": "assistant",
                "content": response,
                "timestamp": time.time(),
            }
        )

        # Mantener solo últimos N mensajes
        history = history[-ConversationMemoryService.WINDOW_SIZE :]
        cache.set(cache_key, history, timeout=ConversationMemoryService.CACHE_TIMEOUT)

    @staticmethod
    def clear_history(user_id: int):
        cache_key = f"bot:conversation:{user_id}"
        cache.delete(cache_key)


__all__ = ["ConversationMemoryService"]
