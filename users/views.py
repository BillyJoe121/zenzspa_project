import logging
import math

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from rest_framework import generics, status, views
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import (BlacklistedToken,
                                                             OutstandingToken)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, UserSession, OTPAttempt, BlockedPhoneNumber
from .permissions import IsVerified, IsAdminUser, IsStaff, IsStaffOrAdmin
from .serializers import (CustomTokenObtainPairSerializer,
                          SessionAwareTokenRefreshSerializer,
                          FlagNonGrataSerializer,
                          PasswordResetConfirmSerializer,
                          PasswordResetRequestSerializer, SimpleUserSerializer,
                          UserRegistrationSerializer, VerifySMSSerializer, StaffListSerializer,
                          UserSessionSerializer)
from .services import TwilioService, verify_recaptcha
from .utils import get_client_ip, register_user_session
from spa.models import Appointment
from core.models import AuditLog, AdminNotification
from notifications.services import NotificationService

logger = logging.getLogger(__name__)

OTP_PHONE_RECAPTCHA_THRESHOLD = getattr(settings, "OTP_PHONE_RECAPTCHA_THRESHOLD", 3)
OTP_IP_RECAPTCHA_THRESHOLD = getattr(settings, "OTP_IP_RECAPTCHA_THRESHOLD", 5)
RECAPTCHA_ACTION_OTP_REQUEST = "auth__otp_request"
RECAPTCHA_ACTION_OTP_VERIFY = "auth__otp_verify"
RECAPTCHA_ACTION_PASSWORD_RESET_REQUEST = "auth__password_reset_request"


def _log_otp_attempt(phone_number, attempt_type, success, request, metadata=None):
    OTPAttempt.objects.create(
        phone_number=phone_number,
        attempt_type=attempt_type,
        is_successful=success,
        ip_address=get_client_ip(request),
        metadata=metadata or {},
    )


def _requires_recaptcha(phone_number, ip_address, attempt_type):
    since = timezone.now() - timedelta(hours=1)
    phone_attempts = OTPAttempt.objects.filter(
        phone_number=phone_number,
        attempt_type=attempt_type,
        created_at__gte=since,
    ).count()
    ip_attempts = OTPAttempt.objects.filter(
        ip_address=ip_address,
        attempt_type=attempt_type,
        created_at__gte=since,
    ).count()
    return phone_attempts >= OTP_PHONE_RECAPTCHA_THRESHOLD or ip_attempts >= OTP_IP_RECAPTCHA_THRESHOLD


def _deactivate_session_for_jti(user, jti):
    UserSession.objects.filter(user=user, refresh_token_jti=jti, is_active=True).update(is_active=False, updated_at=timezone.now())


def _revoke_all_sessions(user):
    tokens = OutstandingToken.objects.filter(user=user)
    for token in tokens:
        try:
            BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            continue
    UserSession.objects.filter(user=user, is_active=True).update(is_active=False, updated_at=timezone.now())

class UserRegistrationView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        request = self.request
        phone_number = serializer.validated_data['phone_number']
        ip = get_client_ip(request)
        if _requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.REQUEST):
            recaptcha_token = request.data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_OTP_REQUEST,
            ):
                raise ValidationError({"recaptcha_token": "Se requiere verificación adicional para continuar."})
        user = serializer.save()
        try:
            twilio_service = TwilioService()
            twilio_service.send_verification_code(user.phone_number)
            _log_otp_attempt(user.phone_number, OTPAttempt.AttemptType.REQUEST, True, request, {"context": "registration"})
        except Exception as e:
            _log_otp_attempt(user.phone_number, OTPAttempt.AttemptType.REQUEST, False, request, {"context": "registration", "error": str(e)})
            user.delete()
            raise


class VerifySMSView(views.APIView):
    permission_classes = [AllowAny]

    MAX_ATTEMPTS = 3
    LOCKOUT_PERIOD_MINUTES = 10
    RECAPTCHA_FAILURE_THRESHOLD = 2

    def post(self, request, *args, **kwargs):
        serializer = VerifySMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        ip = get_client_ip(request)

        cache_key_attempts = f'otp_attempts_{phone_number}'
        cache_key_lockout = f'otp_lockout_{phone_number}'

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

        if attempts >= self.RECAPTCHA_FAILURE_THRESHOLD or _requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.VERIFY):
            recaptcha_token = serializer.validated_data.get('recaptcha_token')
            if not recaptcha_token or not verify_recaptcha(
                recaptcha_token,
                ip,
                action=RECAPTCHA_ACTION_OTP_VERIFY,
            ):
                return Response({"error": "Debes completar la verificación reCAPTCHA para continuar."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)

            if is_valid:
                cache.delete(cache_key_attempts)
                cache.delete(cache_key_lockout)

                user = CustomUser.objects.get(phone_number=phone_number)
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                # El código necesario
                _log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, True, request)

                # --- CORRECCIÓN: Generar y devolver tokens ---
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
                    cache.set(cache_key_attempts, attempts, timeout=timedelta(minutes=self.LOCKOUT_PERIOD_MINUTES).total_seconds())
                _log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"reason": "invalid_code"})
                return Response({"error": "El código de verificación es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            _log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"reason": "user_not_found"})
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            _log_otp_attempt(phone_number, OTPAttempt.AttemptType.VERIFY, False, request, {"error": str(e)})
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = SessionAwareTokenRefreshSerializer


class PasswordResetRequestView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        ip = get_client_ip(request)

        if _requires_recaptcha(phone_number, ip, OTPAttempt.AttemptType.REQUEST):
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
            _log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, True, request, {"context": "password_reset"})
        except Exception as e:
            _log_otp_attempt(phone_number, OTPAttempt.AttemptType.REQUEST, False, request, {"context": "password_reset", "error": str(e)})
            print(f"Error al enviar SMS de reseteo (vía Verify) a {phone_number}: {e}")

        return Response(
            {"detail": "Si existe una cuenta asociada a este número, recibirás un código de verificación."},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        password = serializer.validated_data['password']

        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)

            if not is_valid:
                return Response({"error": "El código es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.get(phone_number=phone_number)
            user.set_password(password)
            user.save()
            _revoke_all_sessions(user)

            return Response({"detail": "Contraseña actualizada correctamente. Por favor inicia sesión nuevamente."}, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentUserView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SimpleUserSerializer

    def get_object(self):
        return self.request.user


class LogoutView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({"error": "Se requiere el token refresh."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
            jti = str(token['jti'])
            _deactivate_session_for_jti(request.user, jti)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            return Response({"error": f"No se pudo cerrar la sesión: {exc}"}, status=status.HTTP_400_BAD_REQUEST)


class LogoutAllView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        _revoke_all_sessions(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FlagNonGrataView(generics.UpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = FlagNonGrataSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'phone_number'

    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()
        new_unusable_password = CustomUser.objects.make_random_password(length=16)
        now = timezone.now()
        
        future_appointments = Appointment.objects.filter(
            user=instance,
            start_time__gte=now,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
                Appointment.AppointmentStatus.RESCHEDULED,
            ],
        )
        future_appointments.update(
            status=Appointment.AppointmentStatus.CANCELLED,
            outcome=Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN,
        )

        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la contraseña temporal del texto que se guarda en el log.
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=instance,
            action=AuditLog.Action.FLAG_NON_GRATA,
            details=f"Usuario marcado como Persona Non Grata. Notas: {serializer.validated_data.get('internal_notes', 'N/A')}"
        )
        AdminNotification.objects.create(
            title="Usuario marcado como CNG",
            message=f"El usuario {instance.phone_number} fue bloqueado por {self.request.user.get_full_name() or self.request.user.phone_number}.",
            notification_type=AdminNotification.NotificationType.USUARIOS,
            subtype=AdminNotification.NotificationSubtype.USUARIO_CNG,
        )

        instance.is_persona_non_grata = True
        instance.is_active = False
        instance.set_password(new_unusable_password)
        
        instance.internal_notes = serializer.validated_data.get('internal_notes', instance.internal_notes)
        instance.internal_photo_url = serializer.validated_data.get('internal_photo_url', instance.internal_photo_url)
        BlockedPhoneNumber.objects.update_or_create(
            phone_number=instance.phone_number,
            defaults={
                'notes': serializer.validated_data.get('internal_notes', instance.internal_notes) or ''
            },
        )

        tokens = OutstandingToken.objects.filter(user=instance)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                continue
        
        instance.save()
        try:
            NotificationService.send_notification(
                user=instance,
                event_code="USER_FLAGGED_NON_GRATA",
                context={
                    "phone_number": instance.phone_number,
                    "notes": instance.internal_notes or "",
                },
                priority="high",
            )
        except Exception:
            logger.exception("No se pudo notificar al usuario %s sobre su estado CNG", instance.phone_number)


class StaffListView(generics.ListAPIView):
    serializer_class = StaffListSerializer
    permission_classes = [IsStaffOrAdmin]

    def get_queryset(self):
        return CustomUser.objects.filter(role=CustomUser.Role.STAFF)


class UserSessionListView(generics.ListAPIView):
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True).order_by('-last_activity')


class UserSessionDeleteView(generics.DestroyAPIView):
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True)

    def perform_destroy(self, instance):
        try:
            token = OutstandingToken.objects.get(jti=instance.refresh_token_jti)
            BlacklistedToken.objects.get_or_create(token=token)
        except OutstandingToken.DoesNotExist:
            pass
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
