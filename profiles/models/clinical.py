import hashlib
import logging
import secrets
import uuid

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.utils import timezone
from fernet_fields import EncryptedTextField
from simple_history.models import HistoricalRecords

from core.models import BaseModel

logger = logging.getLogger(__name__)


class Dosha(models.TextChoices):
    VATA = "VATA", "Vata"
    PITTA = "PITTA", "Pitta"
    KAPHA = "KAPHA", "Kapha"
    UNKNOWN = "UNKNOWN", "Desconocido"


class ClinicalProfile(BaseModel):
    """
    Perfil clínico principal del usuario.
    """

    class Element(models.TextChoices):
        EARTH = "EARTH", "Tierra"
        WATER = "WATER", "Agua"
        FIRE = "FIRE", "Fuego"
        AIR = "AIR", "Aire"
        ETHER = "ETHER", "Éter"

    class Diet(models.TextChoices):
        OMNIVORE = "OMNIVORE", "Omnívora"
        VEGETARIAN = "VEGETARIAN", "Vegetariana"
        VEGAN = "VEGAN", "Vegana"
        OTHER = "OTHER", "Otra"

    class SleepQuality(models.TextChoices):
        GOOD = "GOOD", "Buena"
        REGULAR = "REGULAR", "Regular"
        POOR = "POOR", "Mala"

    class ActivityLevel(models.TextChoices):
        SEDENTARY = "SEDENTARY", "Sedentaria"
        LIGHT = "LIGHT", "Ligera"
        MODERATE = "MODERATE", "Moderada"
        HIGH = "HIGH", "Alta (Atleta)"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    dosha = models.CharField(
        max_length=7,
        choices=Dosha.choices,
        default=Dosha.UNKNOWN,
        verbose_name="Dosha Dominante",
    )
    element = models.CharField(
        max_length=10, choices=Element.choices, blank=True, verbose_name="Elemento Dominante"
    )
    diet_type = models.CharField(
        max_length=15, choices=Diet.choices, blank=True, verbose_name="Tipo de Dieta"
    )
    sleep_quality = models.CharField(
        max_length=10, choices=SleepQuality.choices, blank=True, verbose_name="Calidad de Sueño"
    )
    activity_level = models.CharField(
        max_length=15, choices=ActivityLevel.choices, blank=True, verbose_name="Nivel de Actividad"
    )
    accidents_notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Notas sobre Accidentes",
    )
    general_notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Notas Generales del Terapeuta",
    )
    medical_conditions = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Condiciones médicas o diagnósticos relevantes",
    )
    allergies = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Alergias conocidas",
    )
    contraindications = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Contraindicaciones",
    )
    history = HistoricalRecords(inherit=True)

    def calculate_dominant_dosha(self):
        scores = {
            Dosha.VATA: 0,
            Dosha.PITTA: 0,
            Dosha.KAPHA: 0,
        }

        answers = self.dosha_answers.select_related("selected_option").all()

        if not answers.exists():
            self.dosha = Dosha.UNKNOWN
            self.save(update_fields=["dosha"])
            return

        for answer in answers:
            option = answer.selected_option
            if option.associated_dosha in scores:
                scores[option.associated_dosha] += option.weight

        dominant_dosha = max(scores, key=scores.get)

        self.dosha = dominant_dosha
        self.save(update_fields=["dosha"])

    def anonymize(self, *, performed_by=None):
        from core.models import AuditLog

        with transaction.atomic():
            unique_suffix = uuid.uuid4().hex[:8]
            user = self.user
            if user:
                user.first_name = "ANONIMIZADO"
                user.last_name = ""
                user.phone_number = f"ANON-{unique_suffix}"
                user.email = f"anon-{unique_suffix}@anonymous.local"
                user.is_active = False
                user.is_verified = False
                user.save(
                    update_fields=[
                        "first_name",
                        "last_name",
                        "phone_number",
                        "email",
                        "is_active",
                        "is_verified",
                        "updated_at",
                    ]
                )

            self.accidents_notes = ""
            self.general_notes = ""
            self.medical_conditions = ""
            self.allergies = ""
            self.contraindications = ""
            self.dosha = Dosha.UNKNOWN
            self.element = ""
            self.diet_type = ""
            self.sleep_quality = ""
            self.activity_level = ""
            self.save(
                update_fields=[
                    "accidents_notes",
                    "general_notes",
                    "medical_conditions",
                    "allergies",
                    "contraindications",
                    "dosha",
                    "element",
                    "diet_type",
                    "sleep_quality",
                    "activity_level",
                    "updated_at",
                ]
            )

            self.history.all().delete()

            self.pains.all().delete()
            self.consents.all().delete()
            self.dosha_answers.all().delete()
            self.kiosk_sessions.all().delete()

            AuditLog.objects.create(
                admin_user=performed_by,
                target_user=user,
                action=AuditLog.Action.CLINICAL_PROFILE_ANONYMIZED,
                details=f"Perfil {self.id} anonimizado completamente (incluye historial)",
            )
            logger.info("Perfil clínico %s anonimizado por %s", self.id, getattr(performed_by, "id", None))

    def __str__(self):
        return f"Perfil Clínico de {self.user.first_name}"

    class Meta:
        verbose_name = "Perfil Clínico"
        verbose_name_plural = "Perfiles Clínicos"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["dosha", "element"]),
        ]


class LocalizedPain(BaseModel):
    class PainLevel(models.TextChoices):
        LOW = "LOW", "Leve"
        MODERATE = "MODERATE", "Moderado"
        HIGH = "HIGH", "Alto"

    class PainPeriodicity(models.TextChoices):
        CONSTANT = "CONSTANT", "Constante"
        OCCASIONAL = "OCCASIONAL", "Ocasional"
        SPECIFIC = "SPECIFIC", "En momentos específicos"

    class BodyPart(models.TextChoices):
        HEAD = "HEAD", "Cabeza"
        NECK = "NECK", "Cuello"
        SHOULDERS = "SHOULDERS", "Hombros"
        UPPER_BACK = "UPPER_BACK", "Espalda Alta"
        LOWER_BACK = "LOWER_BACK", "Espalda Baja"
        CHEST = "CHEST", "Pecho"
        ABDOMEN = "ABDOMEN", "Abdomen"
        HIPS = "HIPS", "Caderas"
        ARMS = "ARMS", "Brazos"
        HANDS = "HANDS", "Manos"
        LEGS = "LEGS", "Piernas"
        KNEES = "KNEES", "Rodillas"
        FEET = "FEET", "Pies"
        OTHER = "OTHER", "Otro"

    profile = models.ForeignKey(ClinicalProfile, on_delete=models.CASCADE, related_name="pains")
    body_part = models.CharField(max_length=100, choices=BodyPart.choices, verbose_name="Parte del Cuerpo")
    pain_level = models.CharField(max_length=10, choices=PainLevel.choices, verbose_name="Nivel de Dolor")
    periodicity = models.CharField(max_length=15, choices=PainPeriodicity.choices, verbose_name="Periodicidad")
    notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(2000)],
        verbose_name="Notas Adicionales",
    )

    def __str__(self):
        return f"Dolor en {self.body_part} para {self.profile.user.first_name}"

    class Meta:
        verbose_name = "Dolor Localizado"
        verbose_name_plural = "Dolores Localizados"
