from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Q

from core.utils.exceptions import BusinessLogicError
from core.models import BaseModel


class StaffAvailability(BaseModel):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, "Monday"
        TUESDAY = 2, "Tuesday"
        WEDNESDAY = 3, "Wednesday"
        THURSDAY = 4, "Thursday"
        FRIDAY = 5, "Friday"
        SATURDAY = 6, "Saturday"
        SUNDAY = 7, "Sunday"

    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role__in": ["STAFF", "ADMIN"]},
        related_name="availabilities",
    )
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        verbose_name = "Staff Availability"
        verbose_name_plural = "Staff Availabilities"
        unique_together = ("staff_member", "day_of_week", "start_time", "end_time")
        ordering = ["staff_member", "day_of_week", "start_time"]

    def __str__(self):
        return f"{self.staff_member.first_name} - {self.get_day_of_week_display()}: {self.start_time} - {self.end_time}"

    def clean(self):
        super().clean()
        if self.start_time >= self.end_time:
            raise ValidationError({"start_time": "La hora de inicio debe ser menor a la hora de fin."})
        if not self.staff_member_id or self.day_of_week is None:
            return
        overlaps = (
            StaffAvailability.objects.filter(
                staff_member=self.staff_member,
                day_of_week=self.day_of_week,
            )
            .exclude(id=self.id)
            .filter(Q(start_time__lt=self.end_time) & Q(end_time__gt=self.start_time))
        )
        if overlaps.exclude(start_time=self.start_time, end_time=self.end_time).exists():
            raise BusinessLogicError(
                detail="El horario seleccionado se solapa con otro bloque existente.",
                internal_code="SRV-002",
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        try:
            return super().save(*args, **kwargs)
        except IntegrityError:
            existing = StaffAvailability.objects.filter(
                staff_member=self.staff_member,
                day_of_week=self.day_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
            ).first()
            if existing:
                self.id = existing.id
                return existing
            raise


class AvailabilityExclusion(BaseModel):
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role__in": ["STAFF", "ADMIN"]},
        related_name="availability_exclusions",
    )
    date = models.DateField(null=True, blank=True, help_text="Fecha específica del bloqueo.")
    day_of_week = models.IntegerField(
        choices=StaffAvailability.DayOfWeek.choices,
        null=True,
        blank=True,
        help_text="Día de la semana para bloqueos recurrentes.",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Availability Exclusion"
        verbose_name_plural = "Availability Exclusions"
        ordering = ["staff_member", "date", "day_of_week", "start_time"]

    def __str__(self):
        target = self.date or self.get_day_of_week_display()
        return f"{self.staff_member} - {target}: {self.start_time}-{self.end_time}"

    def clean(self):
        super().clean()
        if self.start_time >= self.end_time:
            raise ValidationError({"start_time": "La hora de inicio debe ser menor a la hora de fin."})
        if not self.date and self.day_of_week is None:
            raise ValidationError("Debe especificar una fecha o un día de la semana para la exclusión.")

    def get_day_of_week_display(self):
        if self.day_of_week is None:
            return None
        return StaffAvailability.DayOfWeek(self.day_of_week).label
