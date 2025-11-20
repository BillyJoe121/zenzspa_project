from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import PromptOrchestrator, GeminiService
from .security import BotSecurityService
from .throttling import BotRateThrottle


class BotWebhookView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BotRateThrottle]

    def post(self, request):
        user = request.user
        security = BotSecurityService(user)

        # ---------------------------------------------------------
        # NIVEL 1: BLOQUEOS PREVIOS (Costo computacional: Muy bajo)
        # ---------------------------------------------------------

        # 1. ¿Está el usuario castigado actualmente?
        is_blocked, reason = security.is_blocked()
        if is_blocked:
            return Response(
                {"reply": reason, "meta": {"blocked": True}},
                status=status.HTTP_403_FORBIDDEN
            )

        user_message = (request.data.get("message") or "").strip()

        # 2. Validación de longitud (Payload size)
        valid_len, len_error = security.validate_input_length(user_message)
        if not valid_len:
            return Response(
                {"error": len_error},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user_message:
            return Response(
                {"error": "El mensaje no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. CHEQUEO DE VELOCIDAD (Protección de Billetera)
        # Si envía muchos mensajes en < 60s, se bloquea por script/bot malicioso.
        if security.check_velocity():
            return Response(
                {"reply": "Estás enviando mensajes demasiado rápido. Acceso pausado por 24h.", "meta": {
                    "blocked": True}},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 4. CHEQUEO DE REPETICIÓN (Fuzzy Matching)
        # Si el mensaje es muy similar a los anteriores.
        if security.check_repetition(user_message):
            return Response(
                {"reply": "Hemos detectado mensajes repetitivos. Acceso pausado por 24h.", "meta": {
                    "blocked": True}},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # ---------------------------------------------------------
        # NIVEL 2: INTELIGENCIA ARTIFICIAL (Costo: Tokens / Latencia)
        # ---------------------------------------------------------

        orchestrator = PromptOrchestrator()
        full_prompt = orchestrator.build_full_prompt(user, user_message)

        gemini = GeminiService()
        # El servicio devuelve directamente el string de respuesta
        reply_text = gemini.generate_response(full_prompt)

        # 5. CHEQUEO DE CONTENIDO (Safety Guardrail)
        # Verificamos si Gemini activó la palabra clave de seguridad "noRelated"
        if "noRelated" in reply_text:
            warning_msg = security.handle_off_topic()

            # Devolvemos la advertencia pre-grabada, NO lo que dijo Gemini
            return Response({
                "reply": warning_msg,
                "meta": {"source": "security_guardrail"}
            })

        # ÉXITO: Mensaje válido y procesado.
        # Nota: Ya NO reseteamos strikes para evitar que abusen alternando mensajes.
        return Response({
            "reply": reply_text,
            "meta": {"source": "gemini-rag"}
        })
