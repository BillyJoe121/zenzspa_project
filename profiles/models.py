from django.db import models
from django.conf import settings
from core.models import BaseModel

class ClinicalProfile(BaseModel):
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

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    dosha = models.CharField(
        max_length=10, choices=Dosha.choices, default=Dosha.UNKNOWN, verbose_name="Dosha Dominante")
    element = models.CharField(
        max_length=10, choices=Element.choices, blank=True, verbose_name="Elemento Dominante")
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

    def calculate_dominant_dosha(self):
        """
        Calcula el Dosha dominante sumando los pesos de las opciones seleccionadas
        en las respuestas del cliente y actualiza el campo 'dosha'.
        """
        scores = {
            self.Dosha.VATA: 0,
            self.Dosha.PITTA: 0,
            self.Dosha.KAPHA: 0,
        }

        answers = self.dosha_answers.select_related('selected_option').all()

        if not answers.exists():
            # Si no hay respuestas, el Dosha es desconocido
            self.dosha = self.Dosha.UNKNOWN
            self.save(update_fields=['dosha'])
            return

        for answer in answers:
            option = answer.selected_option
            if option.associated_dosha in scores:
                scores[option.associated_dosha] += option.weight
        
        # Encontramos el Dosha con la puntuación más alta
        # Si hay un empate, max() devolverá la primera clave que encuentre
        dominant_dosha = max(scores, key=scores.get)

        self.dosha = dominant_dosha
        self.save(update_fields=['dosha'])


    def __str__(self):
        return f"Perfil Clínico de {self.user.first_name}"

    class Meta:
        verbose_name = "Perfil Clínico"
        verbose_name_plural = "Perfiles Clínicos"


class LocalizedPain(BaseModel):
    class PainLevel(models.TextChoices):
        LOW = 'LOW', 'Leve'
        MODERATE = 'MODERATE', 'Moderado'
        HIGH = 'HIGH', 'Alto'

    class PainPeriodicity(models.TextChoices):
        CONSTANT = 'CONSTANT', 'Constante'
        OCCASIONAL = 'OCCASIONAL', 'Ocasional'
        SPECIFIC = 'SPECIFIC', 'En momentos específicos'

    profile = models.ForeignKey(
        ClinicalProfile, on_delete=models.CASCADE, related_name='pains')
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


class Dosha(models.TextChoices):
    VATA = 'VATA', 'Vata'
    PITTA = 'PITTA', 'Pitta'
    KAPHA = 'KAPHA', 'Kapha'

class DoshaQuestion(BaseModel):
    text = models.TextField(unique=True, verbose_name="Texto de la Pregunta")
    category = models.CharField(max_length=50, verbose_name="Categoría (ej. Físico, Mental)", default="General")
    
    def __str__(self):
        return f"[{self.category}] {self.text[:50]}..."

    class Meta:
        verbose_name = "Pregunta de Dosha"
        verbose_name_plural = "Preguntas de Dosha"
        ordering = ['category', 'created_at']

class DoshaOption(BaseModel):
    question = models.ForeignKey(
        DoshaQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255, verbose_name="Texto de la Opción")
    associated_dosha = models.CharField(
        max_length=5, choices=Dosha.choices, verbose_name="Dosha Asociado")
    weight = models.PositiveIntegerField(default=1, verbose_name="Peso/Puntuación")

    def __str__(self):
        return f"{self.associated_dosha}: {self.text[:40]}..."

    class Meta:
        verbose_name = "Opción de Respuesta Dosha"
        verbose_name_plural = "Opciones de Respuesta Dosha"
        unique_together = ('question', 'associated_dosha')
        ordering = ['question', 'created_at']

class ClientDoshaAnswer(BaseModel):
    profile = models.ForeignKey(
        ClinicalProfile, on_delete=models.CASCADE, related_name='dosha_answers')
    question = models.ForeignKey(
        DoshaQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(
        DoshaOption, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Respuesta de Cliente al Cuestionario"
        verbose_name_plural = "Respuestas de Clientes al Cuestionario"
        unique_together = ('profile', 'question')

