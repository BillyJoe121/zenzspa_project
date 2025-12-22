"""
Vistas de autenticación: registro, verificación SMS y tokens JWT.
"""
import logging
import math
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from ..models import CustomUser, OTPAttempt
from ..permissions import IsVerified
from ..serializers import (
    CustomTokenObtainPairSerializer,
    SessionAwareTokenRefreshSerializer,
    SimpleUserSerializer,
    UserRegistrationSerializer,
    VerifySMSSerializer,
)
from ..services import TwilioService, verify_recaptcha
from ..utils import get_client_ip, register_user_session
from profiles.models import ClinicalProfile
from notifications.models import NotificationPreference
from .utils import (
    log_otp_attempt,
    requires_recaptcha,
    RECAPTCHA_ACTION_OTP_REQUEST,
    RECAPTCHA_ACTION_OTP_VERIFY,
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


class VerifySMSView(views.APIView):
    """Verificación de código SMS con protección contra abuso."""
    permission_classes = [AllowAny]

    MAX_ATTEMPTS = 3
    LOCKOUT_PERIOD_MINUTES = 10
    RECAPTCHA_FAILURE_THRESHOLD = 2
    MAX_IP_ATTEMPTS = 20
    MAX_GLOBAL_ATTEMPTS = 1000
    RATE_LIMIT_WINDOW_SECONDS = 3600

    def post(self, request, *args, **kwargs):
        serializer = VerifySMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        ip = get_client_ip(request) or "unknown"

        if cache.get(f"blocked_ip:{ip}"):
            return Response(
                {"detail": "IP temporalmente bloqueada.", "code": "OTP_IP_BLOCKED"},
                status=status.HTTP_403_FORBIDDEN,
            )

        cache_key_attempts = f'otp_attempts_{phone_number}'
        cache_key_lockout = f'otp_lockout_{phone_number}'
        ip_cache_key = f'otp_ip_attempts_{ip}'
        global_cache_key = 'otp_global_attempts'

        if cache.get(cache_key_lockout):
            ttl_seconds = None
            if hasattr(cache, 'ttl'):
                try:
                    ttl_seconds = cache.ttl(cache_key_lockout)
                except Exception:
                    ttl_seconds = None
            if not ttl_seconds:
                ttl_seconds = self.LOCKOUT_PERIOD_MINUTES * 60
            minutes = max(1, math.ceil(ttl_seconds / 60))
            return Response(
                {"error": f"Demasiados intentos. Por favor, inténtalo de nuevo en aproximadamente {minutes} minuto(s)."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        attempts = cache.get(cache_key_attempts, 0)
        ip_attempts = cache.get(ip_cache_key, 0)
        global_attempts = cache.get(global_cache_key, 0)

        if ip_attempts >= self.MAX_IP_ATTEMPTS:
            return Response(
                {
                    "detail": "Demasiados intentos desde esta IP. Intenta más tarde.",
                    "code": "OTP_IP_LOCKED",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if global_attempts >= self.MAX_GLOBAL_ATTEMPTS:
            logger.critical(
                "Rate limit global OTP excedido para verify: %s intentos recientes",
                global_attempts,
            )
            return Response(
                {
                    "detail": "Servicio de verificación temporalmente no disponible.",
                    "code": "OTP_GLOBAL_LIMIT",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cache.set(ip_cache_key, ip_attempts + 1, timeout=self.RATE_LIMIT_WINDOW_SECONDS)
        cache.set(global_cache_key, global_attempts + 1, timeout=self.RATE_LIMIT_WINDOW_SECONDS)

        if attempts >= self.RECAPTCHA_FAILURE_THRESHOLD or requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.VERIFY):
            recaptcha_token = serializer.validated_data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_OTP_VERIFY,
            ):
                return Response({"error": "Debes completar la verificación reCAPTCHA para continuar."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(phone_number, code)

            if is_valid:
                cache.delete(cache_key_attempts)
                cache.delete(cache_key_lockout)
                cache.delete(ip_cache_key)

                user = CustomUser.objects.get(phone_number=phone_number)
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                # Aseguramos recursos dependientes creados en caso de registros previos incompletos
                ClinicalProfile.objects.get_or_create(user=user)
                NotificationPreference.for_user(user)

                log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, True, request)

                # Generar y devolver tokens
                refresh = RefreshToken.for_user(user)
                register_user_session(
                    user=user,
                    refresh_token_jti=str(refresh['jti']),
                    request=request,
                    sender=self.__class__,
                )
                return Response({
                    "detail": "Usuario verificado correctamente.",
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }, status=status.HTTP_200_OK)
            else:
                attempts += 1
                if attempts >= self.MAX_ATTEMPTS:
                    cache.set(cache_key_lockout, True, timedelta(minutes=self.LOCKOUT_PERIOD_MINUTES).total_seconds())
                    cache.delete(cache_key_attempts)
                else:
                    backoff_seconds = min(self.LOCKOUT_PERIOD_MINUTES * 60, attempts * 30)
                    cache.set(cache_key_attempts, attempts, timeout=backoff_seconds)
                log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"reason": "invalid_code"})
                return Response({"error": "El código de verificación es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"reason": "user_not_found"})
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"error": str(e)})
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Vista personalizada para obtener tokens JWT."""
    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """Vista personalizada para refrescar tokens JWT."""
    serializer_class = SessionAwareTokenRefreshSerializer


class CurrentUserView(generics.RetrieveAPIView):
    """Obtiene información del usuario actual autenticado."""
    permission_classes = [IsAuthenticated]
    serializer_class = SimpleUserSerializer

    def get_object(self):
        return self.request.user


class UserDeleteView(views.APIView):
    """
    Permite al usuario eliminar su propia cuenta (GDPR).
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        user = request.user
        # Soft delete
        user.is_active = False
        user.is_deleted = True
        user.phone_number = f"{user.phone_number}_deleted_{timezone.now().timestamp()}"
        user.email = f"deleted_{timezone.now().timestamp()}_{user.email}"
        user.save()
        
        # Revoke sessions
        from .utils import revoke_all_sessions
        revoke_all_sessions(user)
        
        logger.info(f"User {user.id} deleted their account.")
        
        return Response(status=status.HTTP_204_NO_CONTENT)
