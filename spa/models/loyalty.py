from django.conf import settings
from django.db import models

from core.models import BaseModel


class LoyaltyRewardLog(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='loyalty_rewards'
    )
    voucher = models.ForeignKey(
        'Voucher',
        on_delete=models.CASCADE,
        related_name='loyalty_rewards',
        null=True,
        blank=True
    )
    credit = models.ForeignKey(
        'finances.ClientCredit',
        on_delete=models.SET_NULL,
        related_name='loyalty_rewards',
        null=True,
        blank=True
    )
    rewarded_at = models.DateField()

    def __str__(self):
        return f"Loyalty reward for {self.user} on {self.rewarded_at}"

