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
    """Webhook para eventos de Twilio."""
    permission_classes = [AllowAny]

    def post(self, request):
        # Validate signature
        from twilio.request_validator import RequestValidator
        from django.conf import settings
        
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')
        # Twilio requires the full URL including query params
        url = request.build_absolute_uri()
        
        # request.POST is a QueryDict, we need a standard dict
        post_vars = request.POST.dict()
        
        if not validator.validate(url, post_vars, signature):
            logger.warning("Invalid Twilio signature")
            return Response(status=status.HTTP_403_FORBIDDEN)

        data = request.data
        logger.info("Twilio Webhook: %s", data)
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
