from rest_framework import serializers
from .models import ClinicalProfile, LocalizedPain, DoshaQuestion, DoshaOption, ClientDoshaAnswer
from users.serializers import SimpleUserSerializer
from users.models import CustomUser


class LocalizedPainSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalizedPain
        fields = ['id', 'body_part', 'pain_level', 'periodicity', 'notes']
        read_only_fields = ['id']


class ClinicalProfileSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    pains = LocalizedPainSerializer(many=True, required=False)

    class Meta:
        model = ClinicalProfile
        fields = [
            'user', 'dosha', 'element', 'diet_type',
            'sleep_quality', 'activity_level', 'accidents_notes',
            'general_notes', 'pains'
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
    