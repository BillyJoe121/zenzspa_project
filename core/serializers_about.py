"""
Serializers para la página "Quiénes Somos".
"""
from rest_framework import serializers
from .models.about import AboutPage, TeamMember, GalleryImage


class TeamMemberSerializer(serializers.ModelSerializer):
    """
    Serializer para miembros del equipo.
    """
    class Meta:
        model = TeamMember
        fields = [
            'id',
            'name',
            'position',
            'bio',
            'photo',
            'order',
            'is_active',
            'email',
            'linkedin_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GalleryImageSerializer(serializers.ModelSerializer):
    """
    Serializer para imágenes de la galería.
    """
    class Meta:
        model = GalleryImage
        fields = [
            'id',
            'image',
            'caption',
            'order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AboutPageSerializer(serializers.ModelSerializer):
    """
    Serializer para la página Quiénes Somos (solo lectura).
    Incluye miembros del equipo y galería.
    """
    team_members = TeamMemberSerializer(
        many=True,
        read_only=True,
        source='teammember_set'
    )
    gallery_images = GalleryImageSerializer(
        many=True,
        read_only=True,
        source='galleryimage_set'
    )
    
    class Meta:
        model = AboutPage
        fields = [
            'id',
            'mission',
            'vision',
            'values',
            'history',
            'team_description',
            'hero_image',
            'phone',
            'email',
            'address',
            'facebook_url',
            'instagram_url',
            'twitter_url',
            'linkedin_url',
            'youtube_url',
            'business_hours',
            'team_members',
            'gallery_images',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AboutPageUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para actualizar la página Quiénes Somos.
    """
    class Meta:
        model = AboutPage
        fields = [
            'mission',
            'vision',
            'values',
            'history',
            'team_description',
            'hero_image',
            'phone',
            'email',
            'address',
            'facebook_url',
            'instagram_url',
            'twitter_url',
            'linkedin_url',
            'youtube_url',
            'business_hours',
        ]
    
    def validate_email(self, value):
        """
        Validar formato de email.
        """
        if value and '@' not in value:
            raise serializers.ValidationError("Email inválido.")
        return value
    
    def validate_phone(self, value):
        """
        Validar formato de teléfono (básico).
        """
        if value and not any(char.isdigit() for char in value):
            raise serializers.ValidationError("El teléfono debe contener números.")
        return value
