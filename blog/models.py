from django.db import models
from django.conf import settings
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


class Category(models.Model):
    """Categorías para organizar los artículos del blog"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True, verbose_name="Descripción")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Etiquetas para clasificar artículos"""
    name = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Etiqueta"
        verbose_name_plural = "Etiquetas"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Article(models.Model):
    """Artículo del blog"""

    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('published', 'Publicado'),
        ('archived', 'Archivado'),
    ]

    # Información básica
    title = models.CharField(max_length=200, verbose_name="Título")
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    subtitle = models.CharField(max_length=300, blank=True, verbose_name="Subtítulo")

    # Contenido
    excerpt = models.TextField(max_length=500, blank=True, verbose_name="Extracto")
    content = models.TextField(verbose_name="Contenido")

    # Imágenes
    # Imágenes
    cover_image = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="URL de imagen de portada"
    )
    cover_image_alt = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Texto alternativo de portada"
    )

    # Clasificación
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles',
        verbose_name="Categoría"
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='articles',
        verbose_name="Etiquetas"
    )

    # Autor
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_articles',
        verbose_name="Autor"
    )
    author_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Nombre del autor (override)"
    )

    # Estado y publicación
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Estado"
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de publicación"
    )

    # SEO
    meta_title = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Meta título (SEO)"
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Meta descripción (SEO)"
    )

    # Métricas
    views_count = models.PositiveIntegerField(default=0, verbose_name="Vistas")
    reading_time_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="Tiempo de lectura (minutos)"
    )

    # Featured
    is_featured = models.BooleanField(default=False, verbose_name="Destacado")
    featured_order = models.PositiveIntegerField(default=0, verbose_name="Orden destacado")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Auditoría
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Artículo"
        verbose_name_plural = "Artículos"
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['-published_at', 'status']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_featured', '-featured_order']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generar slug si no existe
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Article.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        # Auto-calcular tiempo de lectura (aprox. 200 palabras por minuto)
        if self.content and not self.reading_time_minutes:
            word_count = len(self.content.split())
            self.reading_time_minutes = max(1, round(word_count / 200))

        # Auto-generar extracto si no existe
        if not self.excerpt and self.content:
            self.excerpt = self.content[:497] + '...' if len(self.content) > 500 else self.content

        # Auto-generar meta campos si no existen
        if not self.meta_title:
            self.meta_title = self.title[:60]
        if not self.meta_description:
            self.meta_description = self.excerpt[:160] if self.excerpt else self.title

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        """Verifica si el artículo está publicado"""
        return self.status == 'published' and self.published_at is not None

    def get_author_display(self):
        """Retorna el nombre del autor a mostrar"""
        if self.author_name:
            return self.author_name
        if self.author:
            # Asumiendo que tu modelo de usuario tiene nombre completo
            return getattr(self.author, 'full_name', str(self.author))
        return "StudioZens"


class ArticleImage(models.Model):
    """Imágenes adicionales para el contenido del artículo"""
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name="Artículo"
    )
    image = models.ImageField(
        upload_to='blog/content/%Y/%m/',
        verbose_name="Imagen"
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Texto alternativo"
    )
    caption = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Descripción"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Orden")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Imagen de artículo"
        verbose_name_plural = "Imágenes de artículos"
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Imagen {self.order} - {self.article.title}"
