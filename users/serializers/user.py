import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.crypto import get_random_string
from rest_framework import serializers

from core.serializers import DataMaskingMixin, DynamicFieldsModelSerializer
from profiles.models import ClinicalProfile
from ..models import BlockedPhoneNumber, CustomUser
from ..tasks import send_non_grata_alert_to_admins

CustomUser = get_user_model()
logger = logging.getLogger(__name__)


class SimpleUserSerializer(DataMaskingMixin, DynamicFieldsModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_superuser",
            "vip_expires_at",
            "vip_auto_renew",
        )
        mask_fields = {
            "phone_number": {"mask_with": "phone", "visible_for": ["STAFF"]},
            "email": {"mask_with": "email", "visible_for": ["STAFF"]},
        }

    def _should_mask_field(self, field_name, config, viewer, instance):
        if viewer and getattr(viewer, "is_authenticated", False) and viewer == instance:
            return False
        return super()._should_mask_field(field_name, config, viewer, instance)


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ["phone_number", "password", "email", "first_name", "last_name", "role"]
        extra_kwargs = {
            "phone_number": {"validators": []},
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
        raise serializers.ValidationError("Un usuario con este número de teléfono ya existe.")

    def create(self, validated_data):
        """Crea el usuario usando create_user para hashear la contraseña correctamente."""
        return CustomUser.objects.create_user(
            phone_number=validated_data["phone_number"],
            password=validated_data["password"],
            email=validated_data.get("email"),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            role=validated_data.get("role", CustomUser.Role.CLIENT),
        )


class AdminUserSerializer(serializers.ModelSerializer):
    """
    Serializer para CRUD administrativo de usuarios.
    Permite crear usuarios y asignar roles/estado.
    Incluye campos calculados como is_vip y datos del perfil clínico (dosha).
    """

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Campo calculado de solo lectura (propiedad del modelo)
    is_vip = serializers.BooleanField(read_only=True)

    # Campo del perfil clínico (dosha dominante)
    dosha = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_superuser",  # Solo lectura, distingue superadmin de admin regular
            "is_active",
            "is_verified",
            "is_vip",  # Solo lectura, calculado desde role y vip_expires_at
            "vip_expires_at",  # Campo real para fecha de expiración VIP
            "vip_auto_renew",
            "is_persona_non_grata",
            "dosha",  # Dosha dominante del perfil clínico
            "created_at",
            "updated_at",
            "password",
        ]
        read_only_fields = ["id", "is_superuser", "is_vip", "dosha", "created_at", "updated_at"]

    def get_dosha(self, obj):
        """Obtiene el dosha dominante del perfil clínico."""
        if hasattr(obj, "profile") and obj.profile:
            return obj.profile.dosha
        return None

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None) or get_random_string(12)
        user = CustomUser.objects.create_user(
            phone_number=validated_data.pop("phone_number"),
            email=validated_data.pop("email", None),
            first_name=validated_data.pop("first_name", ""),
            password=password,
            **validated_data,
        )

        # Crear perfil clínico para clientes y VIPs
        if user.role in [CustomUser.Role.CLIENT, CustomUser.Role.VIP]:
            ClinicalProfile.objects.get_or_create(user=user)

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
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
        raise serializers.ValidationError("Un usuario con este número de teléfono ya existe.")
