"""
Vistas de webhooks externos: Twilio, Email verification.
"""
import logging

from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import CustomUser

logger = logging.getLogger(__name__)


class TwilioWebhookView(views.APIView):
    """
    Webhook para eventos de Twilio con validación de firma.

    Recibe y valida webhooks de Twilio verificando la firma HMAC-SHA1
    para garantizar que las peticiones provienen realmente de Twilio.

    Security:
        - Valida firma usando TWILIO_AUTH_TOKEN
        - Rechaza peticiones con firma inválida (HTTP 403)
        - Usa AllowAny porque la autenticación es por firma

    Referencias:
        https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Procesa webhook de Twilio después de validar su firma.

        Returns:
            Response: HTTP 200 si la firma es válida y se procesa correctamente
            Response: HTTP 403 si la firma es inválida
        """
        # Importar en tiempo de ejecución para evitar dependencias circulares
        from twilio.request_validator import RequestValidator
        from django.conf import settings

        # Validar firma de Twilio
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

        # Twilio requiere la URL completa incluyendo query params para la validación
        url = request.build_absolute_uri()

        # Convertir request.POST (QueryDict) a dict estándar para validación
        post_vars = request.POST.dict()

        # Validar firma HMAC-SHA1
        if not validator.validate(url, post_vars, signature):
            logger.warning(
                "Twilio webhook rejected: invalid signature from %s",
                request.META.get('REMOTE_ADDR', 'unknown')
            )
            return Response(
                {"detail": "Invalid signature"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Firma válida, procesar webhook
        data = request.data
        logger.info("Twilio Webhook received: %s", data)

        # TODO: Implementar lógica de procesamiento de eventos específicos de Twilio
        # Por ejemplo: delivery status, message status, call status, etc.

        return Response(status=status.HTTP_200_OK)


class EmailVerificationView(views.APIView):
    """Verifica el email del usuario mediante token."""
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uidb64')
        token = request.data.get('token')

        if not uidb64 or not token:
            return Response({"error": "Faltan parámetros."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            return Response({"error": "Usuario inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if default_token_generator.check_token(user, token):
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            return Response({"detail": "Email verificado correctamente."}, status=status.HTTP_200_OK)

        return Response({"error": "Token inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)
