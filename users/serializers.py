# Reemplaza todo el contenido de zenzspa_project/users/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import CustomUser
from .tasks import send_non_grata_alert_to_admins
from profiles.models import UserProfile
from core.serializers import DynamicFieldsModelSerializer  # <- IMPORTACIÓN AÑADIDA


CustomUser = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializador personalizado para el login que añade una validación extra.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_verified:
            raise serializers.ValidationError({
                "detail": "El número de teléfono no ha sido verificado. Por favor, completa la verificación por SMS."
            })
        return data


class SimpleUserSerializer(DynamicFieldsModelSerializer): # <- HEREDA DE LA NUEVA CLASE
    class Meta:
        model = CustomUser
        fields = ('phone_number', 'first_name', 'last_name', 'role')
        
        # Define qué campos son restringidos y para qué rol mínimo
        role_based_fields = {
            # Solo los ADMINS pueden ver el número de teléfono en listados generales.
            # El propio usuario lo verá en su vista /me/, pero no en listados.
            'ADMIN': ['phone_number']
        }


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, style={'input_type': 'password'}, validators=[validate_password])

    class Meta:
        model = CustomUser
        # CORRECCIÓN: Se ha eliminado 'id' de la lista de campos.
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
        UserProfile.objects.create(user=user)
        return user


class VerifySMSSerializer(serializers.Serializer):
    """
    Valida los datos para la verificación de SMS.
    """
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)

# --- SERIALIZADORES PARA RESETEO DE CONTRASEÑA ---


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Valida el número de teléfono para iniciar el proceso de reseteo de contraseña.
    """
    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value, is_active=True).exists():
            raise serializers.ValidationError(
                "No existe una cuenta activa con este número de teléfono.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Valida todos los campos necesarios para confirmar el cambio de contraseña.
    """
    phone_number = serializers.CharField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password])


class FlagNonGrataSerializer(serializers.ModelSerializer):
    """
    Serializador para marcar a un usuario como "Persona Non Grata".
    """
    class Meta:
        model = CustomUser
        fields = ['is_persona_non_grata', 'profile_picture']
        extra_kwargs = {
            'is_persona_non_grata': {'read_only': True}
        }

# --- SERIALIZADOR AÑADIDO ---


class StaffListSerializer(serializers.ModelSerializer):
    """
    Serializador para listar la información pública y segura del personal.
    """
    class Meta:
        model = CustomUser
        # Campos que se mostrarán para cada miembro del staff
        fields = ['phone_number', 'first_name', 'last_name', 'role']
