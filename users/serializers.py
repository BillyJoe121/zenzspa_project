import logging

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.core.cache import cache

from .models import CustomUser, UserSession, BlockedPhoneNumber, BlockedDevice
from .tasks import send_non_grata_alert_to_admins
# --- INICIO DE LA MODIFICACIÓN ---
from profiles.models import ClinicalProfile # Se actualiza la importación
# --- FIN DE LA MODIFICACIÓN ---
from core.serializers import DataMaskingMixin, DynamicFieldsModelSerializer
from .utils import register_user_session
from .services import verify_recaptcha
from django.utils.crypto import get_random_string


CustomUser = get_user_model()
logger = logging.getLogger(__name__)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
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
                "event": "auth.login_success"
            }
        )
        
        data['role'] = self.user.role
        refresh_token = data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                jti = str(token['jti'])
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
        refresh = self.token_class(attrs['refresh'])
        jti = str(refresh[api_settings.JTI_CLAIM])
        try:
            session = UserSession.objects.get(refresh_token_jti=jti, is_active=True)
        except UserSession.DoesNotExist:
            raise serializers.ValidationError(
                {"detail": "Token inválido o revocado.", "code": "token_not_valid"}
            )

        data = super().validate(attrs)

        new_refresh_token = data.get("refresh")
        if new_refresh_token:
            new_refresh = self.token_class(new_refresh_token)
            session.refresh_token_jti = str(new_refresh[api_settings.JTI_CLAIM])
        session.last_activity = timezone.now()
        session.save(update_fields=['refresh_token_jti', 'last_activity'])
        return data


class SimpleUserSerializer(DataMaskingMixin, DynamicFieldsModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 'role')
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
        write_only=True, style={'input_type': 'password'})
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'password', 'email', 'first_name', 'last_name', 'role']
        extra_kwargs = {
            'phone_number': {'validators': []},
        }

    def validate_email(self, value):
        if value and CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este correo electrónico ya está registrado.")
        return value

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

    def create(self, validated_data):
        """Crea el usuario usando create_user para hashear la contraseña correctamente."""
        return CustomUser.objects.create_user(
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            email=validated_data.get('email'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', CustomUser.Role.CLIENT),
        )


class AdminUserSerializer(serializers.ModelSerializer):
    """
    Serializer para CRUD administrativo de usuarios.
    Permite crear usuarios y asignar roles/estado.
    """
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'phone_number',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_active',
            'is_verified',
            'is_persona_non_grata',
            'vip_auto_renew',
            'password',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password', None) or get_random_string(12)
        user = CustomUser.objects.create_user(
            phone_number=validated_data.pop('phone_number'),
            email=validated_data.pop('email', None),
            first_name=validated_data.pop('first_name', ''),
            password=password,
            **validated_data,
        )
        return user


    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


    def validate_password(self, value):
        """
        MEJORA #13: Política de contraseñas fortalecida con validaciones granulares.
        Valida longitud, complejidad y uso de caracteres especiales.
        """
        # Aplicar validadores estándar de Django
        validate_password(value)

        errors = []

        # Longitud mínima
        if len(value) < 8:
            errors.append("Debe tener al menos 8 caracteres.")

        # Al menos una mayúscula
        if not any(c.isupper() for c in value):
            errors.append("Debe incluir al menos una letra mayúscula.")

        # Al menos una minúscula
        if not any(c.islower() for c in value):
            errors.append("Debe incluir al menos una letra minúscula.")

        # Al menos un dígito
        if not any(c.isdigit() for c in value):
            errors.append("Debe incluir al menos un número.")

        # Al menos un símbolo
        if not any(c in "!@#$%^&*(),.?\":{}|<>_-+=[]\\;'/~`" for c in value):
            errors.append("Debe incluir al menos un símbolo (!@#$%^&*, etc.).")

        if errors:
            raise serializers.ValidationError({
                "password": "Contraseña insegura. " + " ".join(errors)
            })

        return value

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
        role = validated_data.pop('role', CustomUser.Role.CLIENT)
        user = CustomUser.objects.create_user(
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            email=validated_data.get('email'),
            role=role,
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
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'role',
            'is_active',
            'is_verified',
        ]


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


class TOTPSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)


class TOTPVerifySerializer(serializers.Serializer):
    token = serializers.CharField(max_length=6, min_length=6)


class UserExportSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'phone_number', 'email', 'first_name', 'last_name', 
            'role', 'is_verified', 'email_verified', 'status', 'created_at', 'last_login'
        ]

    def get_status(self, obj):
        if obj.is_persona_non_grata:
            return "CNG"
        if not obj.is_active:
            return "Inactivo"
        return "Activo"
