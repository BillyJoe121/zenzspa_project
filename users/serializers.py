from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import CustomUser
from .tasks import send_non_grata_alert_to_admins
# --- INICIO DE LA MODIFICACIÓN ---
from profiles.models import ClinicalProfile # Se actualiza la importación
# --- FIN DE LA MODIFICACIÓN ---
from core.serializers import DynamicFieldsModelSerializer


CustomUser = get_user_model()


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
        return data


class SimpleUserSerializer(DynamicFieldsModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'phone_number', 'email', 'first_name', 'last_name', 'role')
        role_based_fields = {
            'ADMIN': ['phone_number', 'email']
        }


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
        # --- INICIO DE LA MODIFICACIÓN ---
        ClinicalProfile.objects.create(user=user) # Se usa el nuevo nombre del modelo
        # --- FIN DE LA MODIFICACIÓN ---
        return user


class VerifySMSSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)


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