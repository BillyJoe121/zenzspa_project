from django.conf import settings
from django.db import models

from core.models import BaseModel


class Payment(BaseModel):
    """Modelo principal para registrar todos los pagos en el sistema."""

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        APPROVED = "APPROVED", "Aprobado"
        DECLINED = "DECLINED", "Declinado"
        ERROR = "ERROR", "Error"
        TIMEOUT = "TIMEOUT", "Sin confirmación"
        PAID_WITH_CREDIT = "PAID_WITH_CREDIT", "Pagado con Saldo a Favor"
        CANCELLED = "CANCELLED", "Cancelado"

    class PaymentType(models.TextChoices):
        ADVANCE = "ADVANCE", "Anticipo de Cita"
        FINAL = "FINAL", "Pago Final de Cita"
        PACKAGE = "PACKAGE", "Compra de Paquete"
        TIP = "TIP", "Propina"
        VIP_SUBSCRIPTION = "VIP_SUBSCRIPTION", "Membresía VIP"
        ORDER = "ORDER", "Orden de Marketplace"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
    )
    appointment = models.ForeignKey(
        "spa.Appointment",
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    order = models.ForeignKey(
        "marketplace.Order",
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    payment_type = models.CharField(
        max_length=30,
        choices=PaymentType.choices,
        default=PaymentType.ADVANCE,
    )
    transaction_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Reference/transaction id from the payment gateway.",
    )
    raw_response = models.JSONField(default=dict, blank=True)

    used_credit = models.ForeignKey(
        "ClientCredit",
        on_delete=models.SET_NULL,
        related_name="used_in_payments",
        null=True,
        blank=True,
        help_text="Crédito usado en este pago (si aplica).",
    )

    customer_legal_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Documento de identidad del pagador (para PSE, etc.)",
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
        help_text="Tipo de documento del pagador",
    )

    tax_vat_in_cents = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="IVA en centavos (incluido en amount, no se suma)",
    )
    tax_consumption_in_cents = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Impuesto al consumo en centavos (incluido en amount)",
    )

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
        help_text="Método de pago utilizado en Wompi",
    )
    payment_method_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Datos adicionales del método de pago (ej: financial_institution_code para PSE)",
    )

    @property
    def is_approved(self):
        return self.status in [self.PaymentStatus.APPROVED, self.PaymentStatus.PAID_WITH_CREDIT]

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at", "status"], name="payment_time_status_idx"),
            models.Index(fields=["user", "created_at"], name="payment_user_time_idx"),
            models.Index(fields=["status", "payment_type"], name="payment_status_type_idx"),
        ]

    def __str__(self):
        return f"Payment {self.id} - {self.amount} ({self.payment_type})"


class PaymentCreditUsage(BaseModel):
    """Registra el uso de créditos en pagos específicos."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="credit_usages",
    )
    credit = models.ForeignKey(
        "ClientCredit",
        on_delete=models.CASCADE,
        related_name="payment_usages",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
