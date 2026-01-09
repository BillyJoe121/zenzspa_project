import hashlib

from django.conf import settings
from django.db import models
from fernet_fields import EncryptedTextField

from core.models import BaseModel


class PaymentToken(BaseModel):
    """Estado de tokens de pago devueltos por Wompi (Nequi, Bancolombia, etc.)."""

    class TokenStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        APPROVED = "APPROVED", "Aprobado"
        DECLINED = "DECLINED", "Declinado"
        ERROR = "ERROR", "Error"

    id = models.BigAutoField(primary_key=True)
    token_id = models.CharField(max_length=255, db_index=True, blank=True, default="")
    token_fingerprint = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA256 del token para idempotencia/lookup sin exponer el valor real.",
    )
    token_secret = EncryptedTextField(
        null=True,
        blank=True,
        help_text="Token de pago cifrado en reposo (Fernet).",
    )
    token_type = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=TokenStatus.choices,
        default=TokenStatus.PENDING,
    )
    customer_email = models.EmailField(blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="payment_tokens",
        null=True,
        blank=True,
    )
    raw_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="payment_token_status_idx"),
            models.Index(fields=["token_type"], name="payment_token_type_idx"),
        ]

    def __str__(self):
        return f"PaymentToken {self.masked_token} ({self.status})"

    @staticmethod
    def fingerprint(token_value: str) -> str:
        raw = (token_value or "").encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def mask_token(token_value: str) -> str:
        if not token_value:
            return ""
        tail = token_value[-4:]
        return f"****{tail}"

    @property
    def masked_token(self) -> str:
        if self.token_id:
            return self.token_id
        if self.token_secret:
            try:
                decrypted = str(self.token_secret)
                return self.mask_token(decrypted)
            except Exception:
                return "****"
        return ""

    @property
    def plain_token(self) -> str | None:
        return self.token_secret or None
