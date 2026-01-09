from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel, SoftDeleteModel

class ProductCategory(SoftDeleteModel):
    """Categoría específica para productos del marketplace."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Productos"
        ordering = ['name']

    def __str__(self):
        return self.name



class Product(BaseModel):
    name = models.CharField(max_length=255, verbose_name="Nombre del Producto")
    description = models.TextField(verbose_name="Descripción")
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si el producto está visible y disponible para la compra."
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        verbose_name="Categoría"
    )
    preparation_days = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Días de Preparación"
    )
    what_is_included = models.TextField(
        blank=True,
        verbose_name="Qué Incluye",
        help_text="Detalle de qué incluye el producto (ingredientes, componentes, etc.)"
    )
    benefits = models.TextField(
        blank=True,
        verbose_name="Beneficios",
        help_text="Beneficios del producto para la piel o salud."
    )
    how_to_use = models.TextField(
        blank=True,
        verbose_name="Modo de Uso",
        help_text="Instrucciones de aplicación o uso del producto."
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="URL de Imagen Externa",
        help_text="URL de la imagen del producto para optimización en frontend (prioridad sobre ProductImage)."
    )

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class ProductVariant(BaseModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants',
        verbose_name="Producto"
    )
    name = models.CharField(
        max_length=120,
        verbose_name="Nombre de la Variante",
        help_text="Identifica la presentación, por ejemplo 50ml."
    )
    sku = models.CharField(
        max_length=60,
        unique=True,
        verbose_name="SKU",
        help_text="Identificador único para integraciones y carrito."
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Regular")
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio para VIPs",
        help_text="Precio con descuento para miembros VIP. Dejar en blanco si no aplica."
    )
    stock = models.PositiveIntegerField(default=0, verbose_name="Cantidad en Stock")
    reserved_stock = models.PositiveIntegerField(default=0, verbose_name="Stock Reservado")
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        verbose_name="Umbral de Stock Bajo",
        help_text="Avisar al admin cuando el stock baje de esta cantidad."
    )
    min_order_quantity = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Mínimo por Orden"
    )
    max_order_quantity = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Máximo por Orden"
    )

    class Meta:
        verbose_name = "Variante de Producto"
        verbose_name_plural = "Variantes de Producto"
        ordering = ['product__name', 'name']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['product', 'stock']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    def clean(self):
        if self.vip_price and self.vip_price >= self.price:
            raise ValidationError("El precio VIP debe ser menor que el precio regular")
        
        if self.max_order_quantity and self.min_order_quantity > self.max_order_quantity:
            raise ValidationError("La cantidad mínima no puede ser mayor que la cantidad máxima.")



class ProductVariantImage(BaseModel):
    """
    Imagen asociada a una variante específica de producto.
    Permite tener múltiples imágenes por variante usando URLs externas.
    """
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name="Variante"
    )
    image_url = models.URLField(
        max_length=500,
        verbose_name="URL de Imagen",
        help_text="URL de la imagen para esta variante."
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Texto Alternativo"
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden de Visualización",
        help_text="Orden en el que se muestra la imagen (menor = primero)"
    )

    class Meta:
        verbose_name = "Imagen de Variante"
        verbose_name_plural = "Imágenes de Variantes"
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"Imagen para {self.variant}"



class ProductImage(BaseModel):
    """
    Imagen secundaria de un producto.
    Puede ser un archivo subido (image) o una URL externa (image_url).
    Al menos uno de los dos debe estar presente.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='product_images/',
        verbose_name="Imagen (archivo)",
        blank=True,
        null=True,
        help_text="Sube una imagen o proporciona una URL externa."
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="URL de Imagen Externa",
        help_text="URL de imagen externa. Se usa si no hay archivo subido."
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name="Imagen Principal"
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Texto Alternativo"
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden de Visualización",
        help_text="Orden en el que se muestra la imagen (menor = primero)"
    )

    class Meta:
        verbose_name = "Imagen de Producto"
        verbose_name_plural = "Imágenes de Producto"
        ordering = ['-is_primary', 'display_order', 'created_at']

    def __str__(self):
        return f"Imagen para {self.product.name}"

    def get_image_url(self):
        """Retorna la URL de la imagen, priorizando el archivo subido."""
        if self.image:
            return self.image.url
        return self.image_url

    def clean(self):
        super().clean()
        
        # Validar que al menos uno de los campos de imagen esté presente
        if not self.image and not self.image_url:
            raise ValidationError(
                "Debes proporcionar una imagen (archivo subido) o una URL de imagen externa."
            )
        
        # Si hay archivo, validar el archivo
        file = self.image
        if not file:
            return
        max_size_mb = 3
        if hasattr(file, "size") and file.size > max_size_mb * 1024 * 1024:
            raise ValidationError({"image": f"El archivo supera el límite de {max_size_mb}MB."})
        content_type = getattr(file, "content_type", "")
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if content_type and content_type not in allowed_types:
            raise ValidationError({"image": "Formato de imagen no permitido. Usa JPEG, PNG o WEBP."})
        # Validar extensión del filename para evitar uploads disfrazados
        filename = getattr(file, "name", "") or ""
        lowered = filename.lower()
        if not lowered.endswith((".jpg", ".jpeg", ".png", ".webp")):
            raise ValidationError({"image": "Extensión de archivo no permitida. Usa JPG, JPEG, PNG o WEBP."})
        # Validar dimensiones para evitar payloads gigantes
        try:
            from PIL import Image
            file.seek(0)
            with Image.open(file) as img:
                width, height = img.size
                if width > 4096 or height > 4096:
                    raise ValidationError({"image": "La imagen excede las dimensiones máximas 4096x4096."})
                if width < 50 or height < 50:
                    raise ValidationError({"image": "La imagen debe tener al menos 50x50 píxeles."})
        except ValidationError:
            raise
        except Exception:
            raise ValidationError({"image": "No se pudo validar la imagen. Asegúrate de que sea un archivo de imagen válido."})
