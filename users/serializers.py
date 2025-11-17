import logging

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import CustomUser, UserSession, BlockedPhoneNumber
from .tasks import send_non_grata_alert_to_admins
# --- INICIO DE LA MODIFICACIÓN ---
from profiles.models import ClinicalProfile # Se actualiza la importación
# --- FIN DE LA MODIFICACIÓN ---
from core.serializers import DataMaskingMixin, DynamicFieldsModelSerializer
from .utils import register_user_session


CustomUser = get_user_model()
logger = logging.getLogger(__name__)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_verified:
            raise serializers.ValidationError({
                "detail": "El número de teléfono no ha sido verificado. Por favor, completa la verificación por SMS."
            })
        data['role'] = self.user.role
        refresh_token = data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                jti = str(token['jti'])
                register_user_session(
                    user=self.user,
                    refresh_token_jti=jti,
                    request=self.context.get('request'),
                    sender=self.__class__,
                )
            except Exception as exc:
                logger.warning("No se pudo registrar la sesión del usuario: %s", exc)
        return data


class SessionAwareTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user = self._get_user_from_refresh(refresh)
        data = {'access': str(refresh.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass

            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            refresh.outstand()
            data['refresh'] = str(refresh)

        if user is not None:
            jti = str(refresh[api_settings.JTI_CLAIM])
            register_user_session(
                user=user,
                refresh_token_jti=jti,
                request=self.context.get('request'),
                sender=self.__class__,
            )
        return data

    def _get_user_from_refresh(self, refresh):
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        if not user_id:
            return None
        user_model = get_user_model()
        try:
            user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except user_model.DoesNotExist:
            return None
        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )
        return user


class SimpleUserSerializer(DataMaskingMixin, DynamicFieldsModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 'role')
        role_based_fields = {
            'ADMIN': ['phone_number', 'email']
        }
        mask_fields = {
            'phone_number': {'mask_with': 'phone', 'visible_for': ['STAFF']},
            'email': {'mask_with': 'email', 'visible_for': ['STAFF']},
        }

    def _should_mask_field(self, field_name, config, viewer, instance):
        if viewer and getattr(viewer, "is_authenticated", False) and viewer == instance:
            return False
        return super()._should_mask_field(field_name, config, viewer, instance)


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, style={'input_type': 'password'}, validators=[validate_password])

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'first_name',
                  'last_name', 'email', 'password']

    def validate_phone_number(self, value):
        if BlockedPhoneNumber.objects.filter(phone_number=value).exists():
            send_non_grata_alert_to_admins.delay(value)
            raise serializers.ValidationError(
                "Este número de teléfono está bloqueado. Contacte al administrador."
            )
        try:
            existing_user = CustomUser.objects.get(phone_number=value)
        except CustomUser.DoesNotExist:
            return value
        if existing_user.is_persona_non_grata:
            send_non_grata_alert_to_admins.delay(value)
            raise serializers.ValidationError(
                "Este número de teléfono está bloqueado. Contacte al administrador."
            )
        raise serializers.ValidationError(
            "Un usuario con este número de teléfono ya existe.")

    @transaction.atomic
    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            email=validated_data.get('email', '')
        )
        
        if user.role in [CustomUser.Role.CLIENT, CustomUser.Role.VIP]:
            ClinicalProfile.objects.create(user=user)
    
        return user


class VerifySMSSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)
    recaptcha_token = serializers.CharField(required=False, allow_blank=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value, is_active=True).exists():
            raise serializers.ValidationError(
                "No existe una cuenta activa con este número de teléfono.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password])


class FlagNonGrataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['internal_notes', 'internal_photo_url']


class StaffListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'role']


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            'id',
            'ip_address',
            'user_agent',
            'last_activity',
            'is_active',
            'created_at',
        ]
        read_only_fields = fields
