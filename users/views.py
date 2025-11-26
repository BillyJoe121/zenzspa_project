import logging
import math

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from django.utils.crypto import get_random_string
from django.contrib.auth.password_validation import validate_password
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
                          UserRegistrationSerializer, VerifySMSSerializer, StaffListSerializer,
                          UserSessionSerializer, TOTPSetupSerializer, TOTPVerifySerializer, UserExportSerializer)
from .services import TwilioService, verify_recaptcha, TOTPService, GeoIPService
from .utils import get_client_ip, register_user_session
from .throttling import AdminRateThrottle
from django.http import HttpResponse
import csv
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

from spa.models import Appointment
from core.models import AuditLog, AdminNotification
from notifications.services import NotificationService
from core.utils import safe_audit_log
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError

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
    """
    MEJORA #20: Revoca todas las sesiones activas del usuario.
    Invalida tokens JWT y sesiones en UserSession para forzar re-autenticación.
    """
    # Invalidar todos los tokens JWT
    tokens = OutstandingToken.objects.filter(user=user)
    for token in tokens:
        try:
            BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            continue

    # Invalidar todas las sesiones activas
    invalidated_sessions = UserSession.objects.filter(
        user=user, is_active=True
    ).update(is_active=False, updated_at=timezone.now())

    if invalidated_sessions:
        logger.info(
            "Sesiones revocadas para %s: %d sesiones invalidadas",
            user.phone_number,
            invalidated_sessions
        )

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
                cache.delete(ip_cache_key)

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
                    backoff_seconds = min(self.LOCKOUT_PERIOD_MINUTES * 60, attempts * 30)
                    cache.set(cache_key_attempts, attempts, timeout=backoff_seconds)
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
        except TokenError as exc:
            return Response({"error": f"No se pudo cerrar la sesión: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Error desconocido al cerrar sesión."}, status=status.HTTP_400_BAD_REQUEST)


class LogoutAllView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        _revoke_all_sessions(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(views.APIView):
    permission_classes = [IsAuthenticated]

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
        _revoke_all_sessions(user)
        return Response({"detail": "Contraseña actualizada. Inicia sesión nuevamente."}, status=status.HTTP_200_OK)


class FlagNonGrataView(generics.UpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = FlagNonGrataSerializer
    permission_classes = [IsAdminUser]
    throttle_classes = [AdminRateThrottle]
    lookup_field = 'phone_number'


    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()
        new_unusable_password = get_random_string(length=16)
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

        # Invalidar todos los tokens JWT existentes
        tokens = OutstandingToken.objects.filter(user=instance)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                continue

        # MEJORA #11: Invalidar todas las sesiones activas del usuario
        invalidated_sessions = UserSession.objects.filter(
            user=instance,
            is_active=True
        ).update(is_active=False)

        if invalidated_sessions:
            logger.info(
                "Usuario CNG: %d sesiones invalidadas para %s",
                invalidated_sessions,
                instance.phone_number
            )

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


class BlockIPView(views.APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        ip = request.data.get("ip")
        ttl = int(request.data.get("ttl", 3600))
        if not ip:
            return Response({"detail": "IP requerida."}, status=status.HTTP_400_BAD_REQUEST)
        cache.set(f"blocked_ip:{ip}", True, timeout=ttl)
        return Response({"detail": f"IP {ip} bloqueada por {ttl} segundos."}, status=status.HTTP_200_OK)


class TOTPSetupView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        secret = TOTPService.generate_secret()
        user.totp_secret = secret
        user.save(update_fields=['totp_secret'])
        
        uri = TOTPService.get_provisioning_uri(user, secret)
        serializer = TOTPSetupSerializer({"secret": secret, "provisioning_uri": uri})
        return Response(serializer.data)


class TOTPVerifyView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']
        user = request.user
        
        if not user.totp_secret:
            return Response({"error": "2FA no configurado."}, status=status.HTTP_400_BAD_REQUEST)
            
        if TOTPService.verify_token(user.totp_secret, token):
            return Response({"detail": "Código verificado correctamente. 2FA activado."}, status=status.HTTP_200_OK)
        
        return Response({"error": "Código inválido."}, status=status.HTTP_400_BAD_REQUEST)


class UserExportView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [AdminRateThrottle]
    queryset = CustomUser.objects.all()
    serializer_class = UserExportSerializer

    def get(self, request, *args, **kwargs):
        if request.query_params.get('format') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['ID', 'Phone', 'Email', 'First Name', 'Last Name', 'Role', 'Status', 'Created At'])
            
            for user in self.get_queryset():
                status_label = "Active" if user.is_active else "Inactive"
                if user.is_persona_non_grata:
                    status_label = "CNG"
                writer.writerow([
                    user.id, user.phone_number, user.email, user.first_name, user.last_name, 
                    user.role, status_label, user.created_at
                ])
            return response
        return super().get(request, *args, **kwargs)


class TwilioWebhookView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        logger.info("Twilio Webhook: %s", data)
        return Response(status=status.HTTP_200_OK)


class EmailVerificationView(views.APIView):
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

