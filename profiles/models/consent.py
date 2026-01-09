import hashlib

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import BaseModel
from .clinical import ClinicalProfile


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
        ordering = ["-version"]

    def __str__(self):
        return f"Consentimiento v{self.version} - {self.title}"


class ConsentDocument(BaseModel):
    profile = models.ForeignKey(
        ClinicalProfile,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    template = models.ForeignKey(
        ConsentTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
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
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["profile", "is_signed"]),
            models.Index(fields=["template_version", "created_at"]),
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
            self.signature_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)
