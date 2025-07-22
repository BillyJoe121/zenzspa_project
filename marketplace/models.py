import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from core.models import BaseModel
from spa.models import Appointment, Voucher, ServiceCategory

class Product(BaseModel):
    name = models.CharField(max_length=255, verbose_name="Nombre del Producto")
    description = models.TextField(verbose_name="Descripción")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Regular")
    vip_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Precio para VIPs",
        help_text="Precio con descuento para miembros VIP. Dejar en blanco si no aplica."
    )
    stock = models.PositiveIntegerField(default=0, verbose_name="Cantidad en Stock")
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

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['stock']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.vip_price and self.vip_price >= self.price:
            raise ValidationError("El precio VIP debe ser menor que el precio regular")

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

class CartItem(BaseModel):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Ítem de Carrito"
        verbose_name_plural = "Ítems de Carrito"
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                name='unique_product_in_cart'
            )
        ]

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

class Order(BaseModel):
    class OrderStatus(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pendiente de Pago'
        PAID = 'PAID', 'Pagada'
        PREPARING = 'PREPARING', 'En Preparación'
        SHIPPED = 'SHIPPED', 'Enviada'
        DELIVERED = 'DELIVERED', 'Entregada'
        CANCELLED = 'CANCELLED', 'Cancelada'
        RETURNED = 'RETURNED', 'Devuelta'

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
    shipping_date = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha de Envío"
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

class OrderItem(BaseModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Orden"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        verbose_name="Producto"
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
        return f"{self.quantity} x {self.product.name}"

    def clean(self):
        if self.quantity_returned > self.quantity:
            raise ValidationError("La cantidad devuelta no puede ser mayor que la comprada")