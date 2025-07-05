# Crea el archivo zenzspa_project/profiles/serializers.py con este contenido

from rest_framework import serializers
from .models import UserProfile, LocalizedPain


class LocalizedPainSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalizedPain
        fields = ['id', 'body_part', 'pain_level', 'periodicity', 'notes']
        read_only_fields = ['id']


class UserProfileSerializer(serializers.ModelSerializer):
    pains = LocalizedPainSerializer(many=True, required=False)
    user_info = serializers.CharField(source='user.first_name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'user_info', 'dosha', 'element', 'diet_type',
            'sleep_quality', 'activity_level', 'accidents_notes',
            'general_notes', 'pains'
        ]

    def update(self, instance, validated_data):
        pains_data = validated_data.pop('pains', None)

        # Actualiza los campos del perfil
        instance = super().update(instance, validated_data)

        # Actualiza o crea los dolores localizados
        if pains_data is not None:
            # Borra los dolores que no vienen en la petición
            pain_ids_to_keep = [item.get('id')
                                for item in pains_data if item.get('id')]
            instance.pains.exclude(id__in=pain_ids_to_keep).delete()

            # Crea o actualiza los dolores
            for pain_data in pains_data:
                pain_id = pain_data.get('id')
                if pain_id:
                    pain_obj = LocalizedPain.objects.get(
                        id=pain_id, profile=instance)
                    LocalizedPainSerializer().update(pain_obj, pain_data)
                else:
                    LocalizedPain.objects.create(profile=instance, **pain_data)

        return instance
