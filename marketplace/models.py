from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import BaseModel
from spa.models import Appointment, Voucher, ServiceCategory

class Product(BaseModel):
    name = models.CharField(max_length=255, verbose_name="Nombre del Producto")
    description = models.TextField(verbose_name="Descripción")
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si el producto está visible y disponible para la compra."
    )
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
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


class InventoryMovement(BaseModel):
    class MovementType(models.TextChoices):
        SALE = 'SALE', 'Venta'
        RETURN = 'RETURN', 'Devolución'
        RESTOCK = 'RESTOCK', 'Reabastecimiento'
        ADJUSTMENT = 'ADJUSTMENT', 'Ajuste'
        RESERVATION = 'RESERVATION', 'Reserva creada'
        RESERVATION_RELEASE = 'RESERVATION_RELEASE', 'Reserva liberada'
        EXPIRED_RESERVATION = 'EXPIRED_RESERVATION', 'Reserva expirada'

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='inventory_movements',
    )
    quantity = models.IntegerField()
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    reference_order = models.ForeignKey(
        'Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_movements',
    )
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_movements_created',
    )

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=["movement_type", "reference_order", "variant"],
                name="unique_movement_per_order_variant_type",
            )
        ]

class ProductImage(BaseModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='product_images/',
        verbose_name="Imagen"
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

    class Meta:
        verbose_name = "Imagen de Producto"
        verbose_name_plural = "Imágenes de Producto"
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"Imagen para {self.product.name}"

    def clean(self):
        super().clean()
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

class Cart(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carts'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Carrito Activo"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Expira el",
        help_text="Fecha límite para considerar el carrito antes de limpiarlo.",
    )

    class Meta:
        verbose_name = "Carrito de Compras"
        verbose_name_plural = "Carritos de Compras"
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_active=True),
                name='unique_active_cart_per_user'
            )
        ]

    def __str__(self):
        return f"Carrito de {self.user.email}"

    def save(self, *args, **kwargs):
        if self.expires_at is None:
            from django.utils import timezone
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

class CartItem(BaseModel):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Ítem de Carrito"
        verbose_name_plural = "Ítems de Carrito"
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'variant'],
                name='unique_variant_in_cart'
            )
        ]

    def __str__(self):
        return f"{self.quantity}x {self.variant}"

class Order(BaseModel):
    class OrderStatus(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pendiente de Pago'
        PAID = 'PAID', 'Pagada'
        PREPARING = 'PREPARING', 'En Preparación'
        SHIPPED = 'SHIPPED', 'Enviada'
        DELIVERED = 'DELIVERED', 'Entregada'
        CANCELLED = 'CANCELLED', 'Cancelada'
        RETURN_REQUESTED = 'RETURN_REQUESTED', 'Devolución Solicitada'
        RETURN_APPROVED = 'RETURN_APPROVED', 'Devolución Aprobada'
        RETURN_REJECTED = 'RETURN_REJECTED', 'Devolución Rechazada'
        REFUNDED = 'REFUNDED', 'Reembolsada'
        FRAUD_ALERT = 'FRAUD_ALERT', 'Alerta de Fraude'

    class DeliveryOptions(models.TextChoices):
        PICKUP = 'PICKUP', 'Recogida en Local'
        DELIVERY = 'DELIVERY', 'Envío a Domicilio'
        ASSOCIATE_TO_APPOINTMENT = 'ASSOCIATE_TO_APPOINTMENT', 'Asociar a Cita Futura'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name="Usuario"
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
        verbose_name="Estado de la Orden"
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Monto Total"
    )
    delivery_option = models.CharField(
        max_length=30,
        choices=DeliveryOptions.choices,
        verbose_name="Opción de Entrega"
    )
    delivery_address = models.TextField(
        blank=True, null=True,
        verbose_name="Dirección de Envío"
    )
    shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        verbose_name="Costo de Envío",
        help_text="Costo de envío aplicado a esta orden"
    )
    associated_appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Cita Asociada"
    )
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Número de Seguimiento"
    )
    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    shipping_date = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha de Envío"
    )
    estimated_delivery_date = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha Estimada de Entrega"
    )
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Voucher Utilizado"
    )
    wompi_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID Transacción Wompi"
    )
    return_reason = models.TextField(blank=True, verbose_name="Motivo de devolución")
    return_requested_at = models.DateTimeField(null=True, blank=True)
    return_request_data = models.JSONField(default=list, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    fraud_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Orden"
        verbose_name_plural = "Órdenes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Orden {self.id} - {self.user.email}"

    def clean(self):
        super().clean()
        if self.delivery_option == self.DeliveryOptions.DELIVERY:
            if not self.delivery_address or len(self.delivery_address.strip()) < 15:
                raise ValidationError({
                    "delivery_address": "La dirección de envío es obligatoria y debe tener al menos 15 caracteres."
                })

            # Validación de nomenclatura colombiana
            import re
            address_lower = self.delivery_address.lower()

            # Debe incluir tipo de vía
            via_types = [
                'calle', 'carrera', 'avenida', 'transversal', 'diagonal',
                'circular', 'autopista', 'manzana', 'vereda', 'kilometro',
                'cra', 'cll', 'av', 'trans', 'diag', 'circ', 'km'
            ]

            if not any(via_type in address_lower for via_type in via_types):
                raise ValidationError({
                    "delivery_address": "La dirección debe incluir el tipo de vía (Calle, Carrera, Avenida, etc.)."
                })

            # Debe tener formato de nomenclatura colombiana
            nomenclatura_pattern = r'\d+\s*[#]\s*\d+[\s\-]\d+'
            if not re.search(nomenclatura_pattern, self.delivery_address):
                raise ValidationError({
                    "delivery_address": "La dirección debe seguir el formato de nomenclatura colombiana (ej: Calle 123 #45-67)."
                })

class OrderItem(BaseModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Orden"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name="Variante"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    price_at_purchase = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Precio al Comprar"
    )
    quantity_returned = models.PositiveIntegerField(
        default=0,
        verbose_name="Cantidad Devuelta"
    )

    class Meta:
        verbose_name = "Ítem de Orden"
        verbose_name_plural = "Ítems de Órdenes"

    def __str__(self):
        return f"{self.quantity} x {self.variant}"

    def clean(self):
        if self.quantity_returned > self.quantity:
            raise ValidationError("La cantidad devuelta no puede ser mayor que la comprada")


class ProductReview(BaseModel):
    """
    Modelo para reseñas de productos.
    Un usuario puede dejar una reseña por producto solo si ha comprado el producto.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name="Producto"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_reviews',
        verbose_name="Usuario"
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
        verbose_name="Orden de Compra",
        help_text="Orden que valida que el usuario compró el producto"
    )
    rating = models.PositiveSmallIntegerField(
        verbose_name="Calificación",
        help_text="Calificación de 1 a 5 estrellas"
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Título de la Reseña",
        blank=True
    )
    comment = models.TextField(
        verbose_name="Comentario",
        blank=True
    )
    is_verified_purchase = models.BooleanField(
        default=False,
        verbose_name="Compra Verificada",
        help_text="Indica si esta reseña proviene de una compra confirmada"
    )
    is_approved = models.BooleanField(
        default=True,
        verbose_name="Aprobada",
        help_text="Los administradores pueden moderar reseñas inapropiadas"
    )
    admin_response = models.TextField(
        blank=True,
        verbose_name="Respuesta del Administrador"
    )

    class Meta:
        verbose_name = "Reseña de Producto"
        verbose_name_plural = "Reseñas de Productos"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'user'],
                name='unique_review_per_user_per_product'
            )
        ]
        indexes = [
            models.Index(fields=['product', 'is_approved']),
            models.Index(fields=['rating']),
        ]

    def __str__(self):
        return f"Reseña de {self.user.email} para {self.product.name} - {self.rating}⭐"

    def clean(self):
        super().clean()
        if self.rating < 1 or self.rating > 5:
            raise ValidationError({"rating": "La calificación debe estar entre 1 y 5 estrellas."})

        if not self.title and not self.comment:
            raise ValidationError("Debes proporcionar al menos un título o un comentario.")

    def save(self, *args, **kwargs):
        # Verificar si es una compra verificada
        if self.order and self.order.status in [
            Order.OrderStatus.DELIVERED,
            Order.OrderStatus.REFUNDED
        ]:
            # Verificar que el producto esté en la orden
            if self.order.items.filter(variant__product=self.product).exists():
                self.is_verified_purchase = True

        super().save(*args, **kwargs)
