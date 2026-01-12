from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class ClientCredit(BaseModel):
    """Saldo a favor del cliente que puede usar en futuros pagos."""

    class CreditStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponible"
        PARTIALLY_USED = "PARTIALLY_USED", "Parcialmente Usado"
        USED = "USED", "Usado"
        EXPIRED = "EXPIRED", "Expirado"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credits",
    )
    originating_payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        related_name="generated_credits",
        null=True,
        blank=True,
    )
    initial_amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=CreditStatus.choices,
        default=CreditStatus.AVAILABLE,
    )
    expires_at = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha de expiración del crédito.",
    )

    def __str__(self):
        return f"Credit {self.id} - {self.user} ({self.remaining_amount})"


class FinancialAdjustment(BaseModel):
    """Ajustes financieros manuales (créditos/débitos) realizados por administradores."""

    class AdjustmentType(models.TextChoices):
        CREDIT = "CREDIT", "Crédito"
        DEBIT = "DEBIT", "Débito"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="financial_adjustments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    adjustment_type = models.CharField(
        max_length=10,
        choices=AdjustmentType.choices,
        default=AdjustmentType.CREDIT,
    )
    reason = models.TextField(blank=True, default="")
    related_payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjustment_related",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_adjustments",
    )

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")

    def __str__(self):
        return f"{self.adjustment_type} {self.amount} for {self.user}"
