from django.conf import settings
from rest_framework import serializers
from .models import (
    ClinicalProfile,
    LocalizedPain,
    DoshaQuestion,
    DoshaOption,
    ClientDoshaAnswer,
    ConsentDocument,
    ConsentTemplate,
    KioskSession,
)
from users.serializers import SimpleUserSerializer
from users.models import CustomUser


class LocalizedPainSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalizedPain
        fields = ['id', 'body_part', 'pain_level', 'periodicity', 'notes']
        read_only_fields = ['id']


class ConsentDocumentSerializer(serializers.ModelSerializer):
    template = serializers.PrimaryKeyRelatedField(read_only=True)
    template_version = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConsentDocument
        fields = [
            'id',
            'template',
            'template_version',
            'document_text',
            'is_signed',
            'signed_at',
            'ip_address',
            'signature_hash',
            'created_at',
        ]
        read_only_fields = fields


class ConsentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentTemplate
        fields = ['id', 'version', 'title', 'body', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ClinicalProfileSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    pains = LocalizedPainSerializer(many=True, required=False)
    consents = ConsentDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = ClinicalProfile
        fields = [
            'user', 'dosha', 'element', 'diet_type',
            'sleep_quality', 'activity_level', 'accidents_notes',
            'general_notes', 'medical_conditions', 'allergies',
            'contraindications', 'pains', 'consents'
        ]

    def update(self, instance, validated_data):
        pains_data = validated_data.pop('pains', None)
        instance = super().update(instance, validated_data)
        if pains_data is not None:
            pain_ids_to_keep = [item.get('id')
                                for item in pains_data if item.get('id')]
            instance.pains.exclude(id__in=pain_ids_to_keep).delete()
            for pain_data in pains_data:
                pain_id = pain_data.get('id')
                if pain_id:
                    pain_obj = LocalizedPain.objects.get(
                        id=pain_id, profile=instance)
                    LocalizedPainSerializer(context=self.context).update(pain_obj, pain_data)
                else:
                    LocalizedPain.objects.create(profile=instance, **pain_data)
        return instance


class DoshaOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoshaOption
        fields = ['id', 'text', 'associated_dosha', 'weight']
        read_only_fields = ['id']


class DoshaQuestionSerializer(serializers.ModelSerializer):
    options = DoshaOptionSerializer(many=True)

    class Meta:
        model = DoshaQuestion
        fields = ['id', 'text', 'category', 'options']
        read_only_fields = ['id']

    def create(self, validated_data):
        options_data = validated_data.pop('options')
        question = DoshaQuestion.objects.create(**validated_data)
        for option_data in options_data:
            DoshaOption.objects.create(question=question, **option_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', None)
        instance.text = validated_data.get('text', instance.text)
        instance.category = validated_data.get('category', instance.category)
        instance.save()
        if options_data is not None:
            option_ids_to_keep = [item.get('id') for item in options_data if item.get('id')]
            instance.options.exclude(id__in=option_ids_to_keep).delete()
            for option_data in options_data:
                option_id = option_data.get('id')
                if option_id:
                    option_obj = DoshaOption.objects.get(id=option_id, question=instance)
                    option_serializer = DoshaOptionSerializer()
                    option_serializer.update(option_obj, option_data)
                else:
                    DoshaOption.objects.create(question=instance, **option_data)
        return instance

# --- INICIO DE LA MODIFICACIÓN ---

class ClientDoshaAnswerSerializer(serializers.ModelSerializer):
    """
    Serializador para una única respuesta del cliente.
    Se espera el ID de la pregunta y el ID de la opción seleccionada.
    """
    question_id = serializers.UUIDField(write_only=True)
    selected_option_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ClientDoshaAnswer
        fields = ('question_id', 'selected_option_id')


class DoshaQuizSubmissionSerializer(serializers.Serializer):
    """
    Serializador para recibir la lista completa de respuestas del cuestionario.
    """
    answers = ClientDoshaAnswerSerializer(many=True)

    def validate(self, data):
        question_ids = [entry["question_id"] for entry in data.get("answers", [])]
        option_ids = [entry["selected_option_id"] for entry in data.get("answers", [])]
        questions = {
            str(q.id): q
            for q in DoshaQuestion.objects.filter(id__in=question_ids).prefetch_related("options")
        }
        options = {
            str(option.id): option
            for option in DoshaOption.objects.filter(id__in=option_ids)
        }
        errors = []
        for idx, entry in enumerate(data.get("answers", [])):
            question_id = str(entry["question_id"])
            option_id = str(entry["selected_option_id"])
            question = questions.get(question_id)
            option = options.get(option_id)
            if not question or not option or option.question_id != question.id:
                errors.append(
                    {
                        "index": idx,
                        "question_id": question_id,
                        "selected_option_id": option_id,
                        "detail": "La opción seleccionada no pertenece a la pregunta indicada.",
                    }
                )
        if errors:
            raise serializers.ValidationError({"answers": errors})
        return data

    def create(self, validated_data):
        # La lógica de creación se manejará en la vista.
        # Este serializador es solo para validación.
        pass

    def update(self, instance, validated_data):
        pass

class KioskStartSessionSerializer(serializers.Serializer):
    """
    Valida el número de teléfono del cliente para iniciar una sesión de quiosco.
    """
    client_phone_number = serializers.CharField()

    def validate_client_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value, role__in=[CustomUser.Role.CLIENT, CustomUser.Role.VIP]).exists():
            raise serializers.ValidationError("No se encontró un cliente con el número de teléfono proporcionado.")
        return value
    

class KioskSessionStatusSerializer(serializers.ModelSerializer):
    expired = serializers.SerializerMethodField()
    secure_screen_url = serializers.SerializerMethodField()
    force_secure_screen = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = KioskSession
        fields = [
            'id',
            'expires_at',
            'status',
            'is_active',
            'locked',
            'last_activity',
            'expired',
            'has_pending_changes',
            'secure_screen_url',
            'force_secure_screen',
            'remaining_seconds',
        ]
        read_only_fields = fields

    def get_expired(self, obj):
        return obj.has_expired

    def get_secure_screen_url(self, obj):
        return getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure")

    def get_force_secure_screen(self, obj):
        return not obj.is_valid

    def get_remaining_seconds(self, obj):
        return obj.remaining_seconds

class ClinicalProfileHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.SerializerMethodField()
    delta = serializers.SerializerMethodField()
    profile_id = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalProfile.history.model
        fields = [
            'id',
            'profile_id',
            'history_id',
            'history_date',
            'history_type',
            'changed_by',
            'delta',
        ]
        read_only_fields = fields

    def get_changed_by(self, obj):
        if obj.history_user:
            return obj.history_user.get_full_name() or obj.history_user.email or str(obj.history_user_id)
        return None

    def get_profile_id(self, obj):
        return getattr(obj, 'id', None)

    def get_delta(self, obj):
        prev = obj.prev_record
        if not prev:
            return []
        diff = obj.diff_against(prev)
        return [
            {'field': change.field, 'old': change.old, 'new': change.new}
            for change in diff.changes
        ]
    
