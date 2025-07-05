from django.db import models
from django.conf import settings
from core.models import BaseModel  # Importar BaseModel


class UserProfile(BaseModel):
    class Dosha(models.TextChoices):
        VATA = 'VATA', 'Vata'
        PITTA = 'PITTA', 'Pitta'
        KAPHA = 'KAPHA', 'Kapha'
        UNKNOWN = 'UNKNOWN', 'Desconocido'

    class Element(models.TextChoices):
        EARTH = 'EARTH', 'Tierra'
        WATER = 'WATER', 'Agua'
        FIRE = 'FIRE', 'Fuego'
        AIR = 'AIR', 'Aire'
        ETHER = 'ETHER', 'Éter'

    class Diet(models.TextChoices):
        OMNIVORE = 'OMNIVORE', 'Omnívora'
        VEGETARIAN = 'VEGETARIAN', 'Vegetariana'
        VEGAN = 'VEGAN', 'Vegana'
        OTHER = 'OTHER', 'Otra'

    class SleepQuality(models.TextChoices):
        GOOD = 'GOOD', 'Buena'
        REGULAR = 'REGULAR', 'Regular'
        POOR = 'POOR', 'Mala'

    class ActivityLevel(models.TextChoices):
        SEDENTARY = 'SEDENTARY', 'Sedentaria'
        LIGHT = 'LIGHT', 'Ligera'
        MODERATE = 'MODERATE', 'Moderada'
        HIGH = 'HIGH', 'Alta (Atleta)'

    # El campo 'id' se hereda de BaseModel. Se elimina la definición explícita.
    # El campo 'user' ya no puede ser primary_key. La relación 1-a-1 se mantiene con unique=True.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    dosha = models.CharField(
        max_length=10, choices=Dosha.choices, default=Dosha.UNKNOWN)
    element = models.CharField(
        max_length=10, choices=Element.choices, blank=True)
    diet_type = models.CharField(
        max_length=15, choices=Diet.choices, blank=True, verbose_name="Tipo de Dieta")
    sleep_quality = models.CharField(
        max_length=10, choices=SleepQuality.choices, blank=True, verbose_name="Calidad de Sueño")
    activity_level = models.CharField(
        max_length=15, choices=ActivityLevel.choices, blank=True, verbose_name="Nivel de Actividad")
    accidents_notes = models.TextField(
        blank=True, verbose_name="Notas sobre Accidentes")
    general_notes = models.TextField(
        blank=True, verbose_name="Notas Generales del Terapeuta")

    # Los campos 'created_at' y 'updated_at' se heredan de BaseModel.

    def __str__(self):
        return f"Perfil de {self.user.first_name}"

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"


class LocalizedPain(BaseModel):
    class PainLevel(models.TextChoices):
        LOW = 'LOW', 'Leve'
        MODERATE = 'MODERATE', 'Moderado'
        HIGH = 'HIGH', 'Alto'

    class PainPeriodicity(models.TextChoices):
        CONSTANT = 'CONSTANT', 'Constante'
        OCCASIONAL = 'OCCASIONAL', 'Ocasional'
        SPECIFIC = 'SPECIFIC', 'En momentos específicos'

    # El campo 'id' se hereda de BaseModel. Se elimina la definición explícita.
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='pains')
    body_part = models.CharField(
        max_length=100, verbose_name="Parte del Cuerpo")
    pain_level = models.CharField(
        max_length=10, choices=PainLevel.choices, verbose_name="Nivel de Dolor")
    periodicity = models.CharField(
        max_length=15, choices=PainPeriodicity.choices, verbose_name="Periodicidad")
    notes = models.TextField(blank=True, verbose_name="Notas Adicionales")

    def __str__(self):
        return f"Dolor en {self.body_part} para {self.profile.user.first_name}"

    class Meta:
        verbose_name = "Dolor Localizado"
        verbose_name_plural = "Dolores Localizados"
