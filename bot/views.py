from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import GeminiService, ActionExecutorService
from .throttling import BotRateThrottle


class BotWebhookView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BotRateThrottle]

    def post(self, request):
        user_message = request.data.get("message")
        gemini = GeminiService()
        result = gemini.generate_response(user_message, user=request.user)
        return Response(result)


class ActionPreviewView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BotRateThrottle]

    def post(self, request):
        executor = ActionExecutorService(request.user)
        try:
            preview = executor.preview_action(request.data)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(preview)


class ActionExecuteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BotRateThrottle]

    def post(self, request):
        executor = ActionExecutorService(request.user)
        try:
            result = executor.execute_action(request.data)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(result)
