from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Promocion(models.Model):
    """
    Modelo para gestionar promociones y pop-ups publicitarios.
    El admin gestiona el contenido visual y la activación de promociones.
    Los descuentos se aplican manualmente cambiando los precios de los servicios.
    """

    TIPO_CHOICES = [
        ('popup', 'Pop-up'),
        ('banner', 'Banner Superior'),
    ]

    PAGINA_CHOICES = [
        ('dashboard', 'Dashboard Cliente'),
        ('home', 'Home Público'),
        ('services', 'Página de Servicios'),
        ('shop', 'Tienda/Productos'),
        ('book', 'Reservas/Agendar'),
    ]

    # Información básica
    titulo = models.CharField(
        max_length=200,
        help_text="Título principal de la promoción (ej: '¡DESCUENTO ESPECIAL!')"
    )
    descripcion = models.TextField(
        help_text="Descripción detallada. Puedes usar HTML básico (<b>, <i>, <br>, etc.)"
    )
    imagen = models.ImageField(
        upload_to='promociones/',
        blank=True,
        null=True,
        help_text="Imagen subida localmente (opcional)."
    )
    imagen_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL de imagen externa (opcional). Tiene prioridad sobre la imagen subida."
    )

    # Configuración de visualización
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default='popup',
        help_text="Tipo de visualización de la promoción"
    )
    paginas = models.JSONField(
        default=list,
        help_text="Lista de páginas donde se mostrará (ej: ['dashboard', 'home', 'services', 'shop', 'book'])"
    )

    # Control de activación
    activa = models.BooleanField(
        default=True,
        help_text="Si está activa, se mostrará a los usuarios"
    )
    fecha_inicio = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Fecha y hora de inicio (opcional). Si se deja vacío, inicia inmediatamente"
    )
    fecha_fin = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Fecha y hora de finalización (opcional). Si se deja vacío, no caduca"
    )

    # Comportamiento del pop-up
    mostrar_siempre = models.BooleanField(
        default=False,
        help_text="Si es False, el pop-up se muestra solo 1 vez por sesión (usa localStorage)"
    )

    # Prioridad y ordenamiento
    prioridad = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Mayor prioridad = se muestra primero (si hay múltiples activas). 0 = menor prioridad"
    )

    # Tracking básico
    veces_mostrada = models.IntegerField(
        default=0,
        editable=False,
        help_text="Contador automático de veces que se ha mostrado"
    )
    veces_clickeada = models.IntegerField(
        default=0,
        editable=False,
        help_text="Contador automático de clics en el botón de acción"
    )

    # Link de acción (opcional)
    link_accion = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL interna o externa (ej: '/servicios' o 'https://...')"
    )
    texto_boton = models.CharField(
        max_length=50,
        default="Ver más",
        help_text="Texto del botón de acción"
    )

    # Metadatos
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"
        ordering = ['-prioridad', '-creada_en']

    def __str__(self):
        estado = "✅ ACTIVA" if self.esta_vigente() else "❌ INACTIVA"
        return f"{estado} - {self.titulo} ({self.get_tipo_display()})"

    def esta_vigente(self):
        """Verifica si la promoción está vigente considerando fechas y estado activo."""
        if not self.activa:
            return False

        ahora = timezone.now()

        # Verificar fecha de inicio
        if self.fecha_inicio and ahora < self.fecha_inicio:
            return False

        # Verificar fecha de fin
        if self.fecha_fin and ahora > self.fecha_fin:
            return False

        return True

    def incrementar_contador_mostrada(self):
        """Incrementa el contador de veces mostrada."""
        self.veces_mostrada += 1
        self.save(update_fields=['veces_mostrada'])

    def incrementar_contador_click(self):
        """Incrementa el contador de clics."""
        self.veces_clickeada += 1
        self.save(update_fields=['veces_clickeada'])

    def paginas_display(self):
        """Retorna las páginas en formato legible para el admin."""
        if not self.paginas:
            return "Ninguna"
        paginas_dict = dict(self.PAGINA_CHOICES)
        return ", ".join([paginas_dict.get(p, p) for p in self.paginas])
    paginas_display.short_description = 'Páginas donde se muestra'
