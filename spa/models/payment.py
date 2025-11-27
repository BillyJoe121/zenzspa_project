from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Payment(BaseModel):
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
        related_name='payments'
    )
    appointment = models.ForeignKey(
        'Appointment',
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
