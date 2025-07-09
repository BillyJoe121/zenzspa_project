from rest_framework import serializers
# --- INICIO DE LA MODIFICACIÓN ---
from .models import ClinicalProfile, LocalizedPain # Se actualiza la importación
from users.serializers import SimpleUserSerializer
# --- FIN DE LA MODIFICACIÓN ---


class LocalizedPainSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalizedPain
        fields = ['id', 'body_part', 'pain_level', 'periodicity', 'notes']
        read_only_fields = ['id']


# --- INICIO DE LA MODIFICACIÓN ---
# Se renombra el serializador para mantener la consistencia
class ClinicalProfileSerializer(serializers.ModelSerializer):
# --- FIN DE LA MODIFICACIÓN ---
    user = SimpleUserSerializer(read_only=True)
    pains = LocalizedPainSerializer(many=True, required=False)

    class Meta:
        # Se actualiza el modelo al que hace referencia
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