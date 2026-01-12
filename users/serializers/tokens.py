import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

from ..models import BlockedDevice, UserSession
from ..services import verify_recaptcha
from ..utils import register_user_session

CustomUser = get_user_model()
logger = logging.getLogger(__name__)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    MAX_LOGIN_ATTEMPTS = 5

    def validate(self, attrs):
        request = self.context.get("request")
        phone_number = attrs.get("phone_number")
        phone_number = attrs.get("phone_number")
        ip = getattr(request, "META", {}).get("REMOTE_ADDR") if request else None
        user_agent = getattr(request, "META", {}).get("HTTP_USER_AGENT", "")

        # Check BlockedDevice
        # Simple fingerprint based on IP + UserAgent for now (can be improved)
        device_fingerprint = f"{ip}|{user_agent}"
        if BlockedDevice.objects.filter(device_fingerprint=device_fingerprint, is_blocked=True).exists():
            raise serializers.ValidationError(
                {"detail": "Tu dispositivo ha sido bloqueado por actividad sospechosa."}
            )

        # Verificar si el usuario existe y está bloqueado (Persona Non Grata)
        # Usamos all_objects para incluir usuarios soft-deleted
        user_check = CustomUser.all_objects.filter(phone_number=phone_number).first()
        if user_check and user_check.is_persona_non_grata:
            raise serializers.ValidationError({
                "detail": "Tu cuenta ha sido bloqueada. Contacta con soporte si crees que es un error.",
                "code": "account_blocked"
            })

        cache_key = f"login_attempts:{phone_number}"
        attempts = cache.get(cache_key, 0)

        # Incrementar contador de intentos antes de validar
        cache.set(cache_key, attempts + 1, timeout=3600)
        recaptcha_token = None
        if attempts >= self.MAX_LOGIN_ATTEMPTS:
            recaptcha_token = (getattr(request, "data", {}) or {}).get("recaptcha_token")
            if not recaptcha_token or not verify_recaptcha(recaptcha_token, remote_ip=ip, action="auth__login"):
                raise serializers.ValidationError({"detail": "Completa reCAPTCHA para continuar."})

        data = super().validate(attrs)
        cache.set(cache_key, 0, timeout=3600)  # reset on success

        if not self.user.is_verified:
            raise serializers.ValidationError({
                "detail": "El número de teléfono no ha sido verificado. Por favor, completa la verificación por SMS."
            })

        # Structured Audit Log
        logger.info(
            "Login successful",
            extra={
                "user_id": self.user.id,
                "phone": self.user.phone_number,
                "ip": ip,
                "event": "auth.login_success",
            },
        )

        data["role"] = self.user.role
        refresh_token = data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                jti = str(token["jti"])
                register_user_session(
                    user=self.user,
                    refresh_token_jti=jti,
                    request=request,
                    sender=self.__class__,
                )
            except Exception as exc:
                logger.warning("No se pudo registrar la sesión del usuario: %s", exc)
        return data


class SessionAwareTokenRefreshSerializer(TokenRefreshSerializer):
    default_error_messages = {
        **TokenRefreshSerializer.default_error_messages,
        "session_not_found": "Token inválido o sesión expirada.",
    }

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        jti = str(refresh[api_settings.JTI_CLAIM])
        user_id = refresh.get("user_id")

        logger.info(
            "[SESSION_REFRESH] Intentando refrescar token - JTI: %s, user_id: %s",
            jti,
            user_id,
        )

        try:
            session = UserSession.objects.get(refresh_token_jti=jti, is_active=True)
            logger.info(
                "[SESSION_REFRESH] Sesión encontrada - ID: %s, User: %s, IP: %s",
                session.id,
                session.user.phone_number,
                session.ip_address,
            )
        except UserSession.DoesNotExist:
            logger.error(
                "[SESSION_REFRESH_FAILED] Sesión NO encontrada - JTI: %s, user_id: %s",
                jti,
                user_id,
            )
            # Buscar sesiones activas para este usuario para debugging
            if user_id:
                try:
                    user = CustomUser.objects.get(phone_number=user_id)
                    active_sessions = UserSession.objects.filter(user=user, is_active=True)
                    logger.error(
                        "[SESSION_DEBUG] Usuario %s tiene %d sesiones activas con JTIs: %s",
                        user.phone_number,
                        active_sessions.count(),
                        [s.refresh_token_jti for s in active_sessions],
                    )
                except CustomUser.DoesNotExist:
                    logger.error("[SESSION_DEBUG] Usuario %s no encontrado", user_id)

            raise serializers.ValidationError(
                {"detail": "Token inválido o revocado.", "code": "token_not_valid"}
            )

        data = super().validate(attrs)

        new_refresh_token = data.get("refresh")
        old_jti = session.refresh_token_jti
        if new_refresh_token:
            new_refresh = self.token_class(new_refresh_token)
            new_jti = str(new_refresh[api_settings.JTI_CLAIM])
            session.refresh_token_jti = new_jti
            logger.info(
                "[SESSION_REFRESH] Token rotado - User: %s, Old JTI: %s, New JTI: %s",
                session.user.phone_number,
                old_jti,
                new_jti,
            )
        session.last_activity = timezone.now()
        session.save(update_fields=["refresh_token_jti", "last_activity"])
        return data
