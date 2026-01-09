from django.conf import settings
from django.db import models

from core.models import BaseModel

from .catalog import ProductVariant

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
