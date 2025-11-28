"""
Modelos del módulo finances.

Incluye todos los modelos relacionados con pagos, créditos, suscripciones
y comisiones del desarrollador.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Payment(BaseModel):
    """Modelo principal para registrar todos los pagos en el sistema."""

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        APPROVED = 'APPROVED', 'Aprobado'
        DECLINED = 'DECLINED', 'Declinado'
        ERROR = 'ERROR', 'Error'
        TIMEOUT = 'TIMEOUT', 'Sin confirmación'
        PAID_WITH_CREDIT = 'PAID_WITH_CREDIT', 'Pagado con Saldo a Favor'

    class PaymentType(models.TextChoices):
        ADVANCE = 'ADVANCE', 'Anticipo de Cita'
        FINAL = 'FINAL', 'Pago Final de Cita'
        PACKAGE = 'PACKAGE', 'Compra de Paquete'
        TIP = 'TIP', 'Propina'
        VIP_SUBSCRIPTION = 'VIP_SUBSCRIPTION', 'Membresía VIP'
        ORDER = 'ORDER', 'Orden de Marketplace'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
        null=True,
        blank=True
    )
    appointment = models.ForeignKey(
        'spa.Appointment',
        on_delete=models.SET_NULL,
        related_name='payments',
        null=True,
        blank=True,
    )
    order = models.ForeignKey(
        'marketplace.Order',
        on_delete=models.SET_NULL,
        related_name='payments',
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    payment_type = models.CharField(
        max_length=30,
        choices=PaymentType.choices,
        default=PaymentType.ADVANCE,
    )
    transaction_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text="Reference/transaction id from the payment gateway."
    )
    raw_response = models.JSONField(default=dict, blank=True)

    used_credit = models.ForeignKey(
        'ClientCredit',
        on_delete=models.SET_NULL,
        related_name='used_in_payments',
        null=True,
        blank=True,
        help_text="Crédito usado en este pago (si aplica)."
    )

    # Customer Data (Wompi)
    customer_legal_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Documento de identidad del pagador (para PSE, etc.)"
    )
    customer_legal_id_type = models.CharField(
        max_length=10,
        blank=True,
        default="",
        choices=[
            ("CC", "Cédula de Ciudadanía"),
            ("CE", "Cédula de Extranjería"),
            ("NIT", "Número de Identificación Tributaria"),
            ("PP", "Pasaporte"),
            ("TI", "Tarjeta de Identidad"),
            ("DNI", "Documento Nacional de Identidad"),
            ("RG", "Carteira de Identidade / Registro Geral"),
            ("OTHER", "Otro"),
        ],
        help_text="Tipo de documento del pagador"
    )

    # Tax Information (Wompi)
    tax_vat_in_cents = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="IVA en centavos (incluido en amount, no se suma)"
    )
    tax_consumption_in_cents = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Impuesto al consumo en centavos (incluido en amount)"
    )

    # Payment Method Info (Wompi)
    payment_method_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=[
            ("CARD", "Tarjeta de Crédito/Débito"),
            ("PSE", "PSE"),
            ("NEQUI", "Nequi"),
            ("BANCOLOMBIA_TRANSFER", "Botón Bancolombia"),
            ("BANCOLOMBIA_QR", "QR Bancolombia"),
            ("DAVIPLATA", "Daviplata"),
            ("BNPL", "Buy Now Pay Later"),
            ("PCOL", "Puntos Colombia"),
        ],
        help_text="Método de pago utilizado en Wompi"
    )
    payment_method_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Datos adicionales del método de pago (ej: financial_institution_code para PSE)"
    )

    @property
    def is_approved(self):
        return self.status in [self.PaymentStatus.APPROVED, self.PaymentStatus.PAID_WITH_CREDIT]

    def __str__(self):
        return f"Payment {self.id} - {self.amount} ({self.payment_type})"


class PaymentCreditUsage(BaseModel):
    """Registra el uso de créditos en pagos específicos."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='credit_usages'
    )
    credit = models.ForeignKey(
        'ClientCredit',
        on_delete=models.CASCADE,
        related_name='payment_usages'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)


class ClientCredit(BaseModel):
    """Saldo a favor del cliente que puede usar en futuros pagos."""

    class CreditStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Disponible'
        PARTIALLY_USED = 'PARTIALLY_USED', 'Parcialmente Usado'
        USED = 'USED', 'Usado'
        EXPIRED = 'EXPIRED', 'Expirado'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credits'
    )
    originating_payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        related_name='generated_credits',
        null=True,
        blank=True
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
        help_text="Fecha de expiración del crédito."
    )

    def __str__(self):
        return f"Credit {self.id} - {self.user} ({self.remaining_amount})"


class FinancialAdjustment(BaseModel):
    """Ajustes financieros manuales (créditos/débitos) realizados por administradores."""

    class AdjustmentType(models.TextChoices):
        CREDIT = 'CREDIT', 'Crédito'
        DEBIT = 'DEBIT', 'Débito'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='financial_adjustments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    adjustment_type = models.CharField(
        max_length=10,
        choices=AdjustmentType.choices,
        default=AdjustmentType.CREDIT
    )
    reason = models.TextField(blank=True, default="")
    related_payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adjustment_related'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_adjustments'
    )

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")

    def __str__(self):
        return f"{self.adjustment_type} {self.amount} for {self.user}"


class SubscriptionLog(BaseModel):
    """Historial de suscripciones VIP del usuario."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription_logs'
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscription_logs'
    )
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return f"SubscriptionLog {self.user} {self.start_date} - {self.end_date}"


class WebhookEvent(BaseModel):
    """Registro de eventos de webhook recibidos de Wompi."""

    class Status(models.TextChoices):
        PROCESSED = "PROCESSED", "Procesado"
        FAILED = "FAILED", "Falló"
        IGNORED = "IGNORED", "Ignorado"

    event_type = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSED
    )
    error_message = models.TextField(blank=True, default="")

    def __str__(self):
        return f"WebhookEvent {self.id} - {self.event_type} - {self.status}"


class CommissionLedger(BaseModel):
    """Comisiones adeudadas al desarrollador por pagos exitosos."""

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
        Payment,
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
