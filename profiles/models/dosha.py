from django.db import models

from core.models import BaseModel

from .clinical import ClinicalProfile, Dosha


class DoshaQuestion(BaseModel):
    text = models.TextField(unique=True, verbose_name="Texto de la Pregunta")
    order = models.IntegerField(default=0, verbose_name="Orden")
    is_active = models.BooleanField(default=True, verbose_name="Activa")
    category = models.CharField(max_length=50, verbose_name="Categoría (ej. Físico, Mental)", default="General")

    def __str__(self):
        return f"[{self.category}] {self.text[:50]}..."

    class Meta:
        verbose_name = "Pregunta de Dosha"
        verbose_name_plural = "Preguntas de Dosha"
        ordering = ["category", "created_at"]


class DoshaOption(BaseModel):
    question = models.ForeignKey(DoshaQuestion, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=255, verbose_name="Texto de la Opción")
    associated_dosha = models.CharField(max_length=7, choices=Dosha.choices, verbose_name="Dosha Asociado")
    weight = models.PositiveIntegerField(default=1, verbose_name="Peso/Puntuación")

    def __str__(self):
        return f"{self.associated_dosha}: {self.text[:40]}..."

    class Meta:
        verbose_name = "Opción de Respuesta Dosha"
        verbose_name_plural = "Opciones de Respuesta Dosha"
        unique_together = ("question", "associated_dosha")
        ordering = ["question", "created_at"]


class ClientDoshaAnswer(BaseModel):
    profile = models.ForeignKey(ClinicalProfile, on_delete=models.CASCADE, related_name="dosha_answers")
    question = models.ForeignKey(DoshaQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(DoshaOption, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Respuesta de Cliente al Cuestionario"
        verbose_name_plural = "Respuestas de Clientes al Cuestionario"
        unique_together = ("profile", "question")
