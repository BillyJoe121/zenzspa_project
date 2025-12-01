from rest_framework import serializers

from core.utils import get_client_ip
from .models import LegalDocument, UserConsent


class LegalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalDocument
        fields = [
            "id",
            "slug",
            "title",
            "body",
            "doc_type",
            "version",
            "is_active",
            "effective_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AdminLegalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalDocument
        fields = [
            "id",
            "slug",
            "title",
            "body",
            "doc_type",
            "version",
            "is_active",
            "effective_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserConsentSerializer(serializers.ModelSerializer):
    document = LegalDocumentSerializer(read_only=True)

    class Meta:
        model = UserConsent
        fields = [
            "id",
            "document",
            "document_version",
            "user",
            "anonymous_id",
            "context_type",
            "context_id",
            "context_label",
            "ip_address",
            "user_agent",
            "accepted_at",
            "is_valid",
        ]
        read_only_fields = fields


class UserConsentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsent
        fields = [
            "document",
            "anonymous_id",
            "context_type",
            "context_id",
            "context_label",
        ]
        extra_kwargs = {
            "context_type": {"required": False},
            "context_id": {"required": False, "allow_blank": True},
            "context_label": {"required": False, "allow_blank": True},
            "anonymous_id": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        document = attrs.get("document")

        if not document:
            raise serializers.ValidationError("Se requiere un documento legal para registrar el consentimiento.")

        if document and not document.is_active:
            raise serializers.ValidationError("El documento ya no está activo.")

        context_type = attrs.get("context_type") or UserConsent.ContextType.GLOBAL
        attrs["context_type"] = context_type

        # Contextos transaccionales deben incluir un contexto explícito
        if context_type in {UserConsent.ContextType.ORDER, UserConsent.ContextType.APPOINTMENT}:
            if not attrs.get("context_id"):
                raise serializers.ValidationError("Se requiere un identificador de contexto (orden/cita) para este consentimiento.")

        # Usuarios anónimos deben aportar fingerprint
        if not (user and getattr(user, "is_authenticated", False)):
            if not attrs.get("anonymous_id"):
                raise serializers.ValidationError("Se requiere un identificador anónimo (fingerprint) para usuarios no autenticados.")

        # Evita duplicados para el mismo contexto/usuario
        filters = {
            "document": document,
            "document_version": document.version if document else None,
            "context_type": context_type,
            "context_id": attrs.get("context_id") or "",
        }
        if user and user.is_authenticated:
            filters["user"] = user
        else:
            filters["anonymous_id"] = attrs.get("anonymous_id") or ""

        if UserConsent.objects.filter(**filters).exists():
            raise serializers.ValidationError("Ya se registró un consentimiento para este contexto.")

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        extra = {
            "user": user if getattr(user, "is_authenticated", False) else None,
            "ip_address": get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", "") if request else "",
            "document_version": validated_data["document"].version,
        }
        return UserConsent.objects.create(**validated_data, **extra)
