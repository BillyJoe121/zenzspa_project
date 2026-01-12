from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import BaseModel, SoftDeleteModel


class ServiceCategory(SoftDeleteModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_low_supervision = models.BooleanField(
        default=False,
        help_text="Enable optimized booking for services not requiring constant supervision.",
    )
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Service(SoftDeleteModel):
    name = models.CharField(max_length=255)
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional discounted price for VIP members.",
    )
    category = models.ForeignKey(
        ServiceCategory,
        related_name="services",
        on_delete=models.PROTECT,
        help_text="Category the service belongs to.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the service is available for booking.",
    )
    what_is_included = models.TextField(blank=True, help_text="Detalle de qué incluye el servicio (pasos, productos, etc.)")
    benefits = models.TextField(blank=True, help_text="Beneficios para la piel (e.g. hidratación, luminosidad)")
    contraindications = models.TextField(blank=True, help_text="Contraindicaciones médicas o de salud.")
    main_media_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="URL de Imagen/Video Principal",
        help_text="URL externa del medio principal del servicio (imagen o video). Prioridad sobre ServiceMedia.",
    )
    is_main_media_video = models.BooleanField(
        default=False,
        verbose_name="¿El medio principal es un video?",
        help_text="Indica si el medio principal es un video en lugar de una imagen.",
    )
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.duration} min)"

    def clean(self):
        super().clean()
        errors = {}
        if self.vip_price is not None and self.price is not None:
            if self.vip_price >= self.price:
                errors["vip_price"] = "El precio VIP debe ser menor que el precio regular."
        if errors:
            raise ValidationError(errors)


class ServiceMedia(BaseModel):
    """
    Medios (imágenes/videos) asociados a un servicio.
    Permite tener múltiples medios por servicio usando URLs externas.
    Puede ser imagen o video.
    """

    class MediaType(models.TextChoices):
        IMAGE = "IMAGE", "Imagen"
        VIDEO = "VIDEO", "Video"

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="media",
        verbose_name="Servicio",
    )
    media_url = models.URLField(max_length=500, verbose_name="URL del Medio", help_text="URL de la imagen o video para este servicio.")
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.IMAGE,
        verbose_name="Tipo de Medio",
        help_text="Tipo de medio: imagen o video.",
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Texto Alternativo",
        help_text="Descripción del medio para accesibilidad.",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden de Visualización",
        help_text="Orden en el que se muestra el medio (menor = primero)",
    )

    class Meta:
        verbose_name = "Medio de Servicio"
        verbose_name_plural = "Medios de Servicio"
        ordering = ["display_order", "created_at"]
        indexes = [models.Index(fields=["service", "display_order"])]

    def __str__(self):
        return f"{self.get_media_type_display()} para {self.service.name}"
