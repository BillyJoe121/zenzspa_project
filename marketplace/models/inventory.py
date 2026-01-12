from django.conf import settings
from django.db import models

from core.models import BaseModel

from .catalog import ProductVariant

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
