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
    VATA = 'VATA', 'Vata'
    PITTA = 'PITTA', 'Pitta'
    KAPHA = 'KAPHA', 'Kapha'
    UNKNOWN = 'UNKNOWN', 'Desconocido'


class ClinicalProfile(BaseModel):
    """
    Perfil clínico principal del usuario.
    """


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
        max_length=7,
        choices=Dosha.choices,
        default=Dosha.UNKNOWN,
        verbose_name="Dosha Dominante",
    )
    element = models.CharField(
        max_length=10, choices=Element.choices, blank=True, verbose_name="Elemento Dominante")
    diet_type = models.CharField(
        max_length=15, choices=Diet.choices, blank=True, verbose_name="Tipo de Dieta")
    sleep_quality = models.CharField(
        max_length=10, choices=SleepQuality.choices, blank=True, verbose_name="Calidad de Sueño")
    activity_level = models.CharField(
        max_length=15, choices=ActivityLevel.choices, blank=True, verbose_name="Nivel de Actividad")
    accidents_notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Notas sobre Accidentes"
    )
    general_notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Notas Generales del Terapeuta"
    )
    medical_conditions = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Condiciones médicas o diagnósticos relevantes"
    )
    allergies = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Alergias conocidas"
    )
    contraindications = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(5000)],
        verbose_name="Contraindicaciones"
    )
    history = HistoricalRecords(inherit=True)

    def calculate_dominant_dosha(self):
        """
        Calcula el Dosha dominante sumando los pesos de las opciones seleccionadas
        en las respuestas del cliente y actualiza el campo 'dosha'.
        """
        scores = {
            Dosha.VATA: 0,
            Dosha.PITTA: 0,
            Dosha.KAPHA: 0,
        }

        answers = self.dosha_answers.select_related('selected_option').all()

        if not answers.exists():
            # Si no hay respuestas, el Dosha es desconocido
            self.dosha = Dosha.UNKNOWN
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

    def anonymize(self, *, performed_by=None):
        """
        Limpia información sensible del perfil y elimina registros relacionados,
        cumpliendo con el derecho al olvido.
        """
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
                user.save(update_fields=[
                    'first_name',
                    'last_name',
                    'phone_number',
                    'email',
                    'is_active',
                    'is_verified',
                    'updated_at',
                ])

            self.accidents_notes = ''
            self.general_notes = ''
            self.medical_conditions = ''
            self.allergies = ''
            self.contraindications = ''
            self.dosha = Dosha.UNKNOWN
            self.element = ''
            self.diet_type = ''
            self.sleep_quality = ''
            self.activity_level = ''
            self.save(update_fields=[
                'accidents_notes',
                'general_notes',
                'medical_conditions',
                'allergies',
                'contraindications',
                'dosha',
                'element',
                'diet_type',
                'sleep_quality',
                'activity_level',
                'updated_at',
            ])

            # CRITICO - Eliminar historial versionado (GDPR compliance)
            self.history.all().delete()

            # Eliminar registros relacionados
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
            logger.info("Perfil clínico %s anonimizado por %s", self.id, getattr(performed_by, 'id', None))

    def __str__(self):
        return f"Perfil Clínico de {self.user.first_name}"

    class Meta:
        verbose_name = "Perfil Clínico"
        verbose_name_plural = "Perfiles Clínicos"
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['dosha', 'element']),
        ]


class LocalizedPain(BaseModel):
    class PainLevel(models.TextChoices):
        LOW = 'LOW', 'Leve'
        MODERATE = 'MODERATE', 'Moderado'
        HIGH = 'HIGH', 'Alto'

    class PainPeriodicity(models.TextChoices):
        CONSTANT = 'CONSTANT', 'Constante'
        OCCASIONAL = 'OCCASIONAL', 'Ocasional'
        SPECIFIC = 'SPECIFIC', 'En momentos específicos'

    class BodyPart(models.TextChoices):
        HEAD = 'HEAD', 'Cabeza'
        NECK = 'NECK', 'Cuello'
        SHOULDERS = 'SHOULDERS', 'Hombros'
        UPPER_BACK = 'UPPER_BACK', 'Espalda Alta'
        LOWER_BACK = 'LOWER_BACK', 'Espalda Baja'
        CHEST = 'CHEST', 'Pecho'
        ABDOMEN = 'ABDOMEN', 'Abdomen'
        HIPS = 'HIPS', 'Caderas'
        ARMS = 'ARMS', 'Brazos'
        HANDS = 'HANDS', 'Manos'
        LEGS = 'LEGS', 'Piernas'
        KNEES = 'KNEES', 'Rodillas'
        FEET = 'FEET', 'Pies'
        OTHER = 'OTHER', 'Otro'

    profile = models.ForeignKey(
        ClinicalProfile, on_delete=models.CASCADE, related_name='pains')
    body_part = models.CharField(
        max_length=100, choices=BodyPart.choices, verbose_name="Parte del Cuerpo")
    pain_level = models.CharField(
        max_length=10, choices=PainLevel.choices, verbose_name="Nivel de Dolor")
    periodicity = models.CharField(
        max_length=15, choices=PainPeriodicity.choices, verbose_name="Periodicidad")
    notes = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(2000)],
        verbose_name="Notas Adicionales"
    )

    def __str__(self):
        return f"Dolor en {self.body_part} para {self.profile.user.first_name}"

    class Meta:
        verbose_name = "Dolor Localizado"
        verbose_name_plural = "Dolores Localizados"


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
        max_length=7, choices=Dosha.choices, verbose_name="Dosha Asociado")
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


class ConsentTemplate(BaseModel):
    """
    Representa una versión del texto legal que los clientes deben firmar.
    """
    version = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Plantilla de Consentimiento"
        verbose_name_plural = "Plantillas de Consentimiento"
        ordering = ['-version']

    def __str__(self):
        return f"Consentimiento v{self.version} - {self.title}"


class ConsentDocument(BaseModel):
    profile = models.ForeignKey(
        ClinicalProfile,
        on_delete=models.CASCADE,
        related_name='consents'
    )
    template = models.ForeignKey(
        ConsentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )
    template_version = models.PositiveIntegerField(null=True, blank=True)
    document_text = models.TextField(verbose_name="Texto legal presentado")
    is_signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    signature_hash = models.CharField(max_length=255, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=255, blank=True, default="")
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_consents",
    )

    class Meta:
        verbose_name = "Consentimiento Clínico"
        verbose_name_plural = "Consentimientos Clínicos"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['profile', 'is_signed']),
            models.Index(fields=['template_version', 'created_at']),
        ]

    def __str__(self):
        if not self.is_signed and self.revoked_at:
            status = "Revocado"
        elif self.is_signed:
            status = "Firmado"
        else:
            status = "Pendiente"
        return f"Consentimiento {status} para {self.profile.user}"

    def save(self, *args, **kwargs):
        if self.template and not self.template_version:
            self.template_version = self.template.version
        if self.template and not self.document_text:
            self.document_text = self.template.body
        if self.document_text:
            payload = f"{self.profile_id}:{self.template_version}:{self.document_text}"
            self.signature_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)


class KioskSession(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activa'
        LOCKED = 'LOCKED', 'Bloqueada'
        COMPLETED = 'COMPLETED', 'Completada'

    profile = models.ForeignKey(
        ClinicalProfile,
        on_delete=models.CASCADE,
        related_name='kiosk_sessions'
    )
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kiosk_sessions_started'
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    has_pending_changes = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Sesión de Quiosco"
        verbose_name_plural = "Sesiones de Quiosco"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['profile', 'created_at']),
            models.Index(fields=['staff_member', 'created_at']),
        ]

    def __str__(self):
        return f"Sesión para {self.profile.user} expira {self.expires_at}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        if self.status == self.Status.ACTIVE:
            self.is_active = True
            self.locked = False
        elif self.status == self.Status.LOCKED:
            self.is_active = False
            self.locked = True
        else:
            self.is_active = False
            self.locked = False
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == self.Status.ACTIVE and not self.has_expired

    @property
    def has_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def remaining_seconds(self):
        delta = (self.expires_at - timezone.now()).total_seconds()
        return max(int(delta), 0)

    def deactivate(self):
        if self.status != self.Status.COMPLETED:
            self.status = self.Status.COMPLETED
            self.has_pending_changes = False
            self.save(update_fields=['status', 'is_active', 'locked', 'has_pending_changes', 'updated_at'])

    def lock(self):
        if self.status != self.Status.LOCKED:
            self.status = self.Status.LOCKED
            self.has_pending_changes = False
            self.save(update_fields=['status', 'is_active', 'locked', 'has_pending_changes', 'updated_at'])

    def mark_expired(self):
        if self.has_expired and self.status == self.Status.ACTIVE:
            self.lock()

    def heartbeat(self):
        if self.status == self.Status.ACTIVE:
            self.last_activity = timezone.now()
            self.save(update_fields=['last_activity', 'updated_at'])

    def mark_pending_changes(self):
        if not self.has_pending_changes:
            self.has_pending_changes = True
            self.save(update_fields=['has_pending_changes', 'updated_at'])

    def clear_pending_changes(self):
        if self.has_pending_changes:
            self.has_pending_changes = False
            self.save(update_fields=['has_pending_changes', 'updated_at'])
