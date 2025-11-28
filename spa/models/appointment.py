from datetime import timedelta
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.exceptions import BusinessLogicError
from core.models import BaseModel, SoftDeleteModel


class ServiceCategory(SoftDeleteModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_low_supervision = models.BooleanField(
        default=False,
        help_text="Enable optimized booking for services not requiring constant supervision."
    )
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Service(SoftDeleteModel):
    name = models.CharField(max_length=255)
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional discounted price for VIP members."
    )
    category = models.ForeignKey(
        ServiceCategory,
        related_name='services',
        on_delete=models.PROTECT,
        help_text="Category the service belongs to."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the service is available for booking."
    )
    history = HistoricalRecords(inherit=True)

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.duration} min)"

    def clean(self):
        super().clean()
        errors = {}
        if self.vip_price is not None and self.price is not None:
            if self.vip_price >= self.price:
                errors['vip_price'] = "El precio VIP debe ser menor que el precio regular."
        if errors:
            raise ValidationError(errors)


class StaffAvailability(BaseModel):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'
        SATURDAY = 6, 'Saturday'
        SUNDAY = 7, 'Sunday'

    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role__in': ['STAFF', 'ADMIN']},
        related_name='availabilities'
    )
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        verbose_name = "Staff Availability"
        verbose_name_plural = "Staff Availabilities"
        unique_together = ('staff_member', 'day_of_week',
                           'start_time', 'end_time')
        ordering = ['staff_member', 'day_of_week', 'start_time']

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
            .filter(
                Q(start_time__lt=self.end_time) &
                Q(end_time__gt=self.start_time)
            )
        )
        # Allow idempotent creation of identical slots but block true overlaps.
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
        limit_choices_to={'role__in': ['STAFF', 'ADMIN']},
        related_name='availability_exclusions',
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
        ordering = ['staff_member', 'date', 'day_of_week', 'start_time']

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


class Appointment(BaseModel):
    class AppointmentStatus(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pendiente de Pago'
        PAID = 'PAID', 'Pago Final Pendiente'
        CONFIRMED = 'CONFIRMED', 'Confirmada'
        RESCHEDULED = 'RESCHEDULED', 'Reagendada'
        COMPLETED = 'COMPLETED', 'Completada'
        CANCELLED = 'CANCELLED', 'Cancelada'

    class AppointmentOutcome(models.TextChoices):
        NONE = 'NONE', 'Sin resultado'
        CANCELLED_BY_CLIENT = 'CANCELLED_BY_CLIENT', 'Cancelada por el Cliente'
        CANCELLED_BY_SYSTEM = 'CANCELLED_BY_SYSTEM', 'Cancelada por el Sistema'
        CANCELLED_BY_ADMIN = 'CANCELLED_BY_ADMIN', 'Cancelada por el Administrador'
        NO_SHOW = 'NO_SHOW', 'No Asistió'
        REFUNDED = 'REFUNDED', 'Reembolsada'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='appointments'
    )
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='attended_appointments',
        limit_choices_to={'role__in': ['STAFF', 'ADMIN']},
        null=True,
        blank=True
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    services = models.ManyToManyField(
        Service,
        through='AppointmentItem',
        related_name='appointments'
    )
    status = models.CharField(
        max_length=40,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.PENDING_PAYMENT
    )
    outcome = models.CharField(
        max_length=40,
        choices=AppointmentOutcome.choices,
        default=AppointmentOutcome.NONE,
    )
    price_at_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Final price for all the services booked in this appointment."
    )
    reschedule_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this appointment has been rescheduled by the client."
    )

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ['-start_time']

    def __str__(self):
        services = ", ".join(item.service.name for item in self.items.all())
        return f"Appointment for {self.user} ({services or 'No services'}) at {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    @property
    def service_duration_minutes(self):
        return sum(item.duration for item in self.items.all())

    @property
    def total_duration_minutes(self):
        return self.service_duration_minutes

    def get_service_names(self):
        return ", ".join(item.service.name for item in self.items.select_related('service'))


class AppointmentItemManager(models.Manager):
    def _apply_defaults(self, obj):
        if obj.duration is None and obj.service:
            obj.duration = obj.service.duration
        if obj.price_at_purchase is None and obj.service:
            # Avoid circular import at module load time.
            try:
                from users.models import CustomUser
                is_vip = (
                    getattr(obj.appointment, "user", None)
                    and getattr(obj.appointment.user, "role", None) == CustomUser.Role.VIP
                )
            except Exception:
                is_vip = False
            if is_vip and obj.service.vip_price is not None:
                obj.price_at_purchase = obj.service.vip_price
            else:
                obj.price_at_purchase = obj.service.price

    def bulk_create(self, objs, **kwargs):
        for obj in objs:
            self._apply_defaults(obj)
        return super().bulk_create(objs, **kwargs)

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        self._apply_defaults(obj)
        obj.save(using=self._db)
        return obj


class AppointmentItem(BaseModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name='items'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name='appointment_items'
    )
    duration = models.PositiveIntegerField(help_text="Duration in minutes captured at booking time.")
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    objects = AppointmentItemManager()

    class Meta:
        verbose_name = "Appointment Item"
        verbose_name_plural = "Appointment Items"

    def __str__(self):
        return f"{self.service.name} ({self.duration} min)"

    def apply_defaults(self):
        AppointmentItem.objects._apply_defaults(self)

    def save(self, *args, **kwargs):
        self.apply_defaults()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.appointment_id and self.service_id:
            # Check if service already exists in this appointment (exclude self)
            exists = AppointmentItem.objects.filter(
                appointment=self.appointment,
                service=self.service
            ).exclude(id=self.id).exists()
            if exists:
                raise ValidationError(f"El servicio '{self.service.name}' ya está incluido en esta cita.")


class WaitlistEntry(BaseModel):
    class Status(models.TextChoices):
        WAITING = 'WAITING', 'En espera'
        OFFERED = 'OFFERED', 'Oferta enviada'
        EXPIRED = 'EXPIRED', 'Oferta expirada'
        CONFIRMED = 'CONFIRMED', 'Confirmada'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='waitlist_entries'
    )
    services = models.ManyToManyField(
        Service,
        related_name='waitlist_entries',
        blank=True,
    )
    desired_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.WAITING,
    )
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    offered_appointment = models.ForeignKey(
        'Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waitlist_offers',
    )

    class Meta:
        verbose_name = "Entrada de Lista de Espera"
        verbose_name_plural = "Lista de Espera"
        ordering = ['created_at']

    def __str__(self):
        return f"Waitlist {self.user} para {self.desired_date}"

    def clean(self):
        super().clean()
        # Validar que existan servicios activos cuando se hayan asignado
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
        self.save(update_fields=['status', 'offered_at', 'offer_expires_at', 'offered_appointment', 'updated_at'])

    def reset_offer(self):
        self.status = self.Status.WAITING
        self.offered_at = None
        self.offer_expires_at = None
        self.offered_appointment = None
        self.save(update_fields=['status', 'offered_at', 'offer_expires_at', 'offered_appointment', 'updated_at'])
