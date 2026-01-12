from django.conf import settings
from django.db import models

from core.models import BaseModel


class SubscriptionLog(BaseModel):
    """Historial de suscripciones VIP del usuario."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription_logs",
    )
    payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_logs",
    )
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return f"SubscriptionLog {self.user} {self.start_date} - {self.end_date}"
