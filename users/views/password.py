"""
Vistas para gestión de contraseñas: reset y cambio.
"""
import logging

from django.contrib.auth.password_validation import validate_password
from rest_framework import status, views
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from core.api.throttling import PasswordChangeThrottle
from ..models import CustomUser, OTPAttempt
from ..serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from ..services import TwilioService, verify_recaptcha
from ..utils import get_client_ip
from .utils import (
    log_otp_attempt,
    requires_recaptcha,
    revoke_all_sessions,
    RECAPTCHA_ACTION_PASSWORD_RESET_REQUEST,
)

logger = logging.getLogger(__name__)


class PasswordResetRequestView(views.APIView):
    """Solicita reset de contraseña enviando código SMS."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        ip = get_client_ip(request)

        if requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.REQUEST):
            recaptcha_token = request.data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_PASSWORD_RESET_REQUEST,
            ):
                raise ValidationError({"recaptcha_token": "Verificación reCAPTCHA requerida para continuar."})

        try:
            twilio_service = TwilioService()
            twilio_service.send_verification_code(phone_number)
            log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, True, request, {"context": "password_reset"})
        except Exception as e:
            log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, False, request, {"context": "password_reset", "error": str(e)})
            print(f"Error al enviar SMS de reseteo (vía Verify) a {phone_number}: {e}")

        return Response(
            {"detail": "Si existe una cuenta asociada a este número, recibirás un código de verificación."},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(views.APIView):
    """Confirma reset de contraseña con código SMS."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        password = serializer.validated_data['password']

        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(phone_number, code)

            if not is_valid:
                return Response({"error": "El código es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.get(phone_number=phone_number)
            user.set_password(password)
            user.save()
            revoke_all_sessions(user)

            return Response({"detail": "Contraseña actualizada correctamente. Por favor inicia sesión nuevamente."}, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangePasswordView(views.APIView):
    """
    Cambia la contraseña del usuario autenticado.

    Implementa rate limiting restrictivo (3 intentos por hora) para proteger
    contra ataques de fuerza bruta en caso de sesión comprometida.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordChangeThrottle]

    def post(self, request, *args, **kwargs):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not old_password or not new_password:
            return Response(
                {"detail": "Debes enviar old_password y new_password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(old_password):
            return Response(
                {"detail": "La contraseña actual es incorrecta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user=user)
        except Exception as exc:
            return Response(
                {"detail": " ".join([str(x) for x in exc])},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        revoke_all_sessions(user)

        return Response({"detail": "Contraseña actualizada. Inicia sesión nuevamente."}, status=status.HTTP_200_OK)
