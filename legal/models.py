from django.conf import settings
from django.db import models

from core.models import BaseModel


class LegalDocument(BaseModel):
    class DocumentType(models.TextChoices):
        GLOBAL_POPUP = "GLOBAL_POPUP", "Términos Generales"
        PROFILE = "PROFILE", "Perfil/Onboarding"
        PURCHASE = "PURCHASE", "Compra/Checkout"
        OTHER = "OTHER", "Otro"

    slug = models.SlugField(max_length=100, help_text="Identificador único legible, ej: terms-and-conditions")
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Contenido renderizable (markdown/HTML)")
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices, default=DocumentType.GLOBAL_POPUP)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    effective_at = models.DateTimeField(null=True, blank=True, help_text="Fecha desde la cual aplica esta versión.")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Documento Legal"
        verbose_name_plural = "Documentos Legales"
        unique_together = (("slug", "version"),)
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug", "version"]),
            models.Index(fields=["doc_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} v{self.version}"

    def save(self, *args, **kwargs):
        is_new_version = False
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).first()
            if old and old.version != self.version:
                is_new_version = True
        else:
            # Documento nuevo cuenta como nueva versión
            is_new_version = True
        result = super().save(*args, **kwargs)
        if is_new_version:
            # Invalidar consentimientos de versiones anteriores del mismo slug
            try:
                from .models import UserConsent  # import local para evitar ciclos al importar
                UserConsent.objects.filter(
                    document__slug=self.slug,
                    document_version__lt=self.version,
                ).update(is_valid=False)
            except Exception:
                pass
        return result


class UserConsent(BaseModel):
    class ContextType(models.TextChoices):
        GLOBAL = "GLOBAL", "Consentimiento Global"
        PROFILE = "PROFILE", "Perfil"
        ORDER = "ORDER", "Orden"
        APPOINTMENT = "APPOINTMENT", "Cita"
        OTHER = "OTHER", "Otro"

    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="consents")
    document_version = models.PositiveIntegerField(help_text="Versión del documento al momento de la aceptación.")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="consents")
    anonymous_id = models.CharField(max_length=64, blank=True, help_text="Identificador temporal/fingerprint para usuarios anónimos.")
    context_type = models.CharField(max_length=20, choices=ContextType.choices, default=ContextType.GLOBAL)
    context_id = models.CharField(max_length=64, blank=True)
    context_label = models.CharField(max_length=120, blank=True, help_text="Texto auxiliar ej: ORDER-1234, PROFILE-UUID.")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    accepted_at = models.DateTimeField(auto_now_add=True)
    is_valid = models.BooleanField(default=True, help_text="Marcado en falso cuando hay nueva versión del documento o se revoca.")

    class Meta:
        verbose_name = "Consentimiento de Usuario"
        verbose_name_plural = "Consentimientos de Usuario"
        ordering = ["-accepted_at"]
        indexes = [
            models.Index(fields=["document", "document_version"]),
            models.Index(fields=["user", "document"]),
            models.Index(fields=["anonymous_id", "document"]),
            models.Index(fields=["context_type", "context_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "document_version", "user", "anonymous_id", "context_type", "context_id"],
                name="unique_user_consent_per_context",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.document_version:
            self.document_version = self.document.version
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.user.email if self.user else self.anonymous_id or "anon"
        return f"{self.document} aceptado por {target} ({self.context_type})"
