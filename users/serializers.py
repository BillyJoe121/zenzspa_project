import logging

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import CustomUser, UserSession
from .tasks import send_non_grata_alert_to_admins
# --- INICIO DE LA MODIFICACIÓN ---
from profiles.models import ClinicalProfile # Se actualiza la importación
# --- FIN DE LA MODIFICACIÓN ---
from core.serializers import DynamicFieldsModelSerializer
from .signals import user_session_logged_in


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
        request = self.context.get('request')
        refresh_token = data.get('refresh')
        if request and refresh_token:
            try:
                token = RefreshToken(refresh_token)
                jti = str(token['jti'])
                ip = self._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:512]
                user_session_logged_in.send(
                    sender=self.__class__,
                    user=self.user,
                    refresh_token_jti=jti,
                    ip_address=ip,
                    user_agent=user_agent,
                )
            except Exception as exc:
                logger.warning("No se pudo registrar la sesión del usuario: %s", exc)
        return data

    def _get_client_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class SimpleUserSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 'role')
        role_based_fields = {
            'ADMIN': ['phone_number', 'email']
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if not viewer or not viewer.is_authenticated:
            data['phone_number'] = self._mask_phone(data.get('phone_number'))
            data['email'] = self._mask_email(data.get('email'))
            return data

        if viewer.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF] or viewer == instance:
            return data

        data['phone_number'] = self._mask_phone(data.get('phone_number'))
        data['email'] = self._mask_email(data.get('email'))
        return data

    @staticmethod
    def _mask_phone(value):
        if not value:
            return value
        return f"{value[:3]}****{value[-2:]}" if len(value) >= 6 else "****"

    @staticmethod
    def _mask_email(value):
        if not value or "@" not in value:
            return value
        local, domain = value.split("@", 1)
        masked_local = local[0] + "***" + local[-1] if len(local) > 2 else "***"
        return f"{masked_local}@{domain}"


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, style={'input_type': 'password'}, validators=[validate_password])

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'first_name',
                  'last_name', 'email', 'password']

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            non_grata_user = CustomUser.objects.filter(
                phone_number=value, is_persona_non_grata=True).first()
            if non_grata_user:
                send_non_grata_alert_to_admins.delay(value)
                raise serializers.ValidationError(
                    "Este número de teléfono está bloqueado. Contacte al administrador."
                )
            raise serializers.ValidationError(
                "Un usuario con este número de teléfono ya existe.")
        return value

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
