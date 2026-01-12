from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from .services import Service


class WaitlistEntry(BaseModel):
    class Status(models.TextChoices):
        WAITING = "WAITING", "En espera"
        OFFERED = "OFFERED", "Oferta enviada"
        EXPIRED = "EXPIRED", "Oferta expirada"
        CONFIRMED = "CONFIRMED", "Confirmada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="waitlist_entries")
    services = models.ManyToManyField(Service, related_name="waitlist_entries", blank=True)
    desired_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    offered_appointment = models.ForeignKey(
        "Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="waitlist_offers",
    )

    class Meta:
        verbose_name = "Entrada de Lista de Espera"
        verbose_name_plural = "Lista de Espera"
        ordering = ["created_at"]

    def __str__(self):
        return f"Waitlist {self.user} para {self.desired_date}"

    def clean(self):
        super().clean()
        if self.pk and not self.services.exists():
            raise ValidationError({"services": "Debes asociar al menos un servicio a la lista de espera."})
        if self.pk:
            inactive = self.services.filter(is_active=False)
            if inactive.exists():
                names = ", ".join(inactive.values_list("name", flat=True))
                raise ValidationError({"services": f"Servicios inactivos no permitidos: {names}"})

    def mark_offered(self, appointment, ttl_minutes):
        now = timezone.now()
        self.status = self.Status.OFFERED
        self.offered_at = now
        self.offer_expires_at = now + timedelta(minutes=ttl_minutes)
        self.offered_appointment = appointment
        self.save(update_fields=["status", "offered_at", "offer_expires_at", "offered_appointment", "updated_at"])

    def reset_offer(self):
        self.status = self.Status.WAITING
        self.offered_at = None
        self.offer_expires_at = None
        self.offered_appointment = None
        self.save(update_fields=["status", "offered_at", "offer_expires_at", "offered_appointment", "updated_at"])
