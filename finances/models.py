from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError

from core.models import BaseModel


class CommissionLedger(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PAID = "PAID", "Pagada"
        FAILED_NSF = "FAILED_NSF", "Fondos insuficientes"

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Monto adeudado al desarrollador por esta transacción.",
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Monto total aplicado a esta comisión.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source_payment = models.ForeignKey(
        "spa.Payment",
        on_delete=models.PROTECT,
        related_name="commission_entries",
        help_text="Pago original que generó la comisión.",
    )
    wompi_transfer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Identificador de la dispersión en Wompi cuando se pague.",
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Momento en que la comisión fue liquidada.",
    )

    class Meta:
        verbose_name = "Comisión del Desarrollador"
        verbose_name_plural = "Comisiones del Desarrollador"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_payment"],
                name="unique_commission_per_payment",
            )
        ]

    @property
    def pending_amount(self) -> Decimal:
        return max(self.amount - (self.paid_amount or Decimal("0.00")), Decimal("0.00"))

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < Decimal("0"):
            raise ValidationError({"amount": "El monto de la comisión no puede ser negativo."})
        if self.paid_amount is not None and self.paid_amount < Decimal("0"):
            raise ValidationError({"paid_amount": "El monto pagado no puede ser negativo."})

    def save(self, *args, **kwargs):
        # Normalizar a 2 decimales
        if self.amount is not None:
            self.amount = self.amount.quantize(Decimal("0.01"))
        if self.paid_amount is not None:
            self.paid_amount = self.paid_amount.quantize(Decimal("0.01"))
        self.full_clean()
        return super().save(*args, **kwargs)
