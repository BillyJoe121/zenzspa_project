from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel

from .catalog import Product
from .orders import Order

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
