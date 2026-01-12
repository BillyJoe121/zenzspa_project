"""
Vistas de registro de usuarios y reenvío de OTP.
"""
import logging

from django.core.cache import cache
from rest_framework import generics, status, views
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from profiles.models import ClinicalProfile
from notifications.models import NotificationPreference
from ..models import CustomUser, OTPAttempt
from ..serializers import UserRegistrationSerializer
from ..services import TwilioService, verify_recaptcha
from ..utils import get_client_ip
from .utils import (
    RECAPTCHA_ACTION_OTP_REQUEST,
    log_otp_attempt,
    requires_recaptcha,
)

logger = logging.getLogger(__name__)


class UserRegistrationView(generics.CreateAPIView):
    """Registro de nuevos usuarios con verificación SMS."""

    queryset = CustomUser.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        request = self.request
        phone_number = serializer.validated_data['phone_number']
        ip = get_client_ip(request)

        if requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.REQUEST):
            recaptcha_token = request.data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_OTP_REQUEST,
            ):
                raise ValidationError({"recaptcha_token": "Se requiere verificación adicional para continuar."})

        user = serializer.save()
        # Garantiza recursos dependientes desde el registro (idempotente por modelos OneToOne)
        ClinicalProfile.objects.get_or_create(user=user)
        NotificationPreference.for_user(user)
        try:
            twilio_service = TwilioService()
            twilio_service.send_verification_code(user.phone_number)
            log_otp_attempt(user.phone_number, OTPAttempt.AttemptType.REQUEST, True, request, {"context": "registration"})
        except Exception as e:
            log_otp_attempt(user.phone_number, OTPAttempt.AttemptType.REQUEST, False, request, {"context": "registration", "error": str(e)})
            user.delete()
            raise


class ResendOTPView(views.APIView):
    """
    Reenvía el código de verificación OTP a usuarios existentes no verificados.
    Endpoint: POST /api/v1/auth/otp/resend/
    """

    permission_classes = [AllowAny]

    # Rate limiting
    RESEND_COOLDOWN_SECONDS = 60  # 1 minuto entre reenvíos
    MAX_RESENDS_PER_HOUR = 5

    def post(self, request, *args, **kwargs):
        phone_number = request.data.get('phone_number')
        ip = get_client_ip(request) or "unknown"

        if not phone_number:
            return Response(
                {"detail": "El número de teléfono es requerido.", "code": "phone_required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar cooldown (evitar spam)
        cooldown_key = f"otp_resend_cooldown:{phone_number}"
        if cache.get(cooldown_key):
            return Response(
                {
                    "detail": "Debes esperar antes de solicitar otro código.",
                    "code": "resend_cooldown",
                    "retry_after_seconds": self.RESEND_COOLDOWN_SECONDS
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Verificar límite por hora
        hourly_key = f"otp_resend_hourly:{phone_number}"
        hourly_count = cache.get(hourly_key, 0)
        if hourly_count >= self.MAX_RESENDS_PER_HOUR:
            return Response(
                {
                    "detail": "Has excedido el límite de reenvíos. Intenta más tarde.",
                    "code": "resend_limit_exceeded"
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Buscar usuario
        try:
            user = CustomUser.objects.get(phone_number=phone_number)
        except CustomUser.DoesNotExist:
            # No revelar si el usuario existe o no por seguridad
            return Response(
                {"detail": "Si el número está registrado, recibirás un código de verificación."},
                status=status.HTTP_200_OK
            )

        # Verificar si ya está verificado
        if user.is_verified:
            return Response(
                {"detail": "Este número ya ha sido verificado.", "code": "already_verified"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar si está bloqueado
        if user.is_persona_non_grata or not user.is_active:
            return Response(
                {"detail": "Tu cuenta ha sido bloqueada.", "code": "account_blocked"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verificar reCAPTCHA si es necesario
        if requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.REQUEST):
            recaptcha_token = request.data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_OTP_REQUEST,
            ):
                return Response(
                    {"detail": "Se requiere verificación reCAPTCHA.", "code": "recaptcha_required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Enviar código OTP
        try:
            twilio_service = TwilioService()
            twilio_service.send_verification_code(user.phone_number)

            # Establecer cooldown y contador
            cache.set(cooldown_key, True, timeout=self.RESEND_COOLDOWN_SECONDS)
            cache.set(hourly_key, hourly_count + 1, timeout=3600)

            log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, True, request, {"context": "resend"})

            return Response(
                {"detail": "Código de verificación enviado exitosamente."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, False, request, {"context": "resend", "error": str(e)})
            logger.exception("Error al reenviar OTP a %s", phone_number)
            return Response(
                {"detail": "Error al enviar el código. Intenta más tarde.", "code": "send_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
