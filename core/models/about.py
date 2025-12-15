"""
Modelo para la página "Quiénes Somos" (About Page).
"""
from django.db import models
from core.models import BaseModel


class AboutPage(BaseModel):
    """
    Modelo Singleton para la página "Quiénes Somos".
    
    Solo debe existir una instancia de este modelo.
    """
    # Contenido principal
    mission = models.TextField(
        verbose_name="Misión",
        help_text="Declaración de la misión de StudioZens",
        blank=True
    )
    vision = models.TextField(
        verbose_name="Visión",
        help_text="Declaración de la visión de StudioZens",
        blank=True
    )
    values = models.TextField(
        verbose_name="Valores",
        help_text="Valores corporativos de StudioZens",
        blank=True
    )
    history = models.TextField(
        verbose_name="Historia",
        help_text="Historia de StudioZens",
        blank=True
    )
    team_description = models.TextField(
        verbose_name="Descripción del Equipo",
        help_text="Descripción general del equipo de trabajo",
        blank=True
    )
    
    # Imágenes
    hero_image = models.ImageField(
        upload_to='about/hero/',
        verbose_name="Imagen Principal",
        help_text="Imagen hero de la página Quiénes Somos",
        null=True,
        blank=True
    )
    
    # Información de contacto
    phone = models.CharField(
        max_length=20,
        verbose_name="Teléfono de Contacto",
        blank=True
    )
    email = models.EmailField(
        verbose_name="Email de Contacto",
        blank=True
    )
    address = models.TextField(
        verbose_name="Dirección",
        blank=True
    )
    
    # Redes sociales
    facebook_url = models.URLField(
        verbose_name="Facebook",
        blank=True
    )
    instagram_url = models.URLField(
        verbose_name="Instagram",
        blank=True
    )
    twitter_url = models.URLField(
        verbose_name="Twitter/X",
        blank=True
    )
    linkedin_url = models.URLField(
        verbose_name="LinkedIn",
        blank=True
    )
    youtube_url = models.URLField(
        verbose_name="YouTube",
        blank=True
    )
    
    # Horarios
    business_hours = models.TextField(
        verbose_name="Horarios de Atención",
        help_text="Horarios de atención al público",
        blank=True,
        default="Lunes a Sábado: 9:00 AM - 8:00 PM\nDomingos: Cerrado"
    )
    
    class Meta:
        verbose_name = "Página Quiénes Somos"
        verbose_name_plural = "Página Quiénes Somos"
    
    def __str__(self):
        return "Página Quiénes Somos"
    
    def save(self, *args, **kwargs):
        """
        Garantizar que solo exista una instancia (Singleton).
        """
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        """
        Obtiene o crea la única instancia de AboutPage.
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class TeamMember(BaseModel):
    """
    Modelo para miembros del equipo mostrados en la página Quiénes Somos.
    """
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre Completo"
    )
    position = models.CharField(
        max_length=200,
        verbose_name="Cargo/Posición"
    )
    bio = models.TextField(
        verbose_name="Biografía",
        help_text="Breve descripción del miembro del equipo",
        blank=True
    )
    photo = models.ImageField(
        upload_to='about/team/',
        verbose_name="Foto",
        null=True,
        blank=True
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden de Visualización",
        help_text="Orden en que aparece en la página (menor = primero)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Mostrar en la página"
    )
    
    # Redes sociales personales (opcional)
    email = models.EmailField(
        verbose_name="Email",
        blank=True
    )
    linkedin_url = models.URLField(
        verbose_name="LinkedIn",
        blank=True
    )
    
    class Meta:
        verbose_name = "Miembro del Equipo"
        verbose_name_plural = "Miembros del Equipo"
        ordering = ['order', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.position}"


class GalleryImage(BaseModel):
    """
    Modelo para galería de imágenes en la página Quiénes Somos.
    """
    image = models.ImageField(
        upload_to='about/gallery/',
        verbose_name="Imagen"
    )
    caption = models.CharField(
        max_length=255,
        verbose_name="Descripción",
        blank=True
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden de Visualización"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa"
    )
    
    class Meta:
        verbose_name = "Imagen de Galería"
        verbose_name_plural = "Imágenes de Galería"
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return self.caption or f"Imagen {self.id}"
