from django.db import models
from django.conf import settings
from core.models import BaseModel

class ServiceCategory(BaseModel):
    """
    Represents a category for services, e.g., 'Masajes', 'Terapias'.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_low_supervision = models.BooleanField(
        default=False,
        help_text="Enable optimized booking for services not requiring constant supervision."
    )

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

class Service(BaseModel):
    """
    Represents a service offered by the spa.
    """
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

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.duration} min)"


class StaffAvailability(BaseModel):
    """
    Defines the weekly working schedule for a staff member.
    """
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


class Appointment(BaseModel):
    """
    Represents a booking of a service by a user with a staff member.
    """
    # --- INICIO DE LA MODIFICACIÓN ---
    class AppointmentStatus(models.TextChoices):
        # Flujo de creación
        PENDING_ADVANCE = 'PENDING_ADVANCE', 'Pendiente de Pago de Anticipo'
        CONFIRMED = 'CONFIRMED', 'Confirmada (Anticipo Pagado)'
        
        # Flujo de finalización
        COMPLETED_PENDING_FINAL_PAYMENT = 'COMPLETED_PENDING_FINAL_PAYMENT', 'Completada (Pago Final Pendiente)'
        COMPLETED = 'COMPLETED', 'Completada y Pagada'

        # Flujo de cancelación
        CANCELLED_BY_CLIENT = 'CANCELLED_BY_CLIENT', 'Cancelada por el Cliente'
        CANCELLED_BY_SYSTEM = 'CANCELLED_BY_SYSTEM', 'Cancelada por el Sistema' # Por falta de pago de anticipo
        CANCELLED_BY_ADMIN = 'CANCELLED_BY_ADMIN', 'Cancelada por el Administrador'

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
        # Se permite que sea nulo para servicios de baja supervisión
        null=True,
        blank=True
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name='appointments')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    status = models.CharField(
        max_length=40,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.PENDING_ADVANCE
    )
    
    # Se renombra el campo para consistencia
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    
    reschedule_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this appointment has been rescheduled by the client."
    )
    # --- FIN DE LA MODIFICACIÓN ---

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ['-start_time']

    def __str__(self):
        return f"Appointment for {self.user} with {self.staff_member or 'N/A'} at {self.start_time.strftime('%Y-%m-%d %H:%M')}" # pylint: disable=no-member


class Package(BaseModel):
    """
    Represents a bundle of services that can be purchased together.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    services = models.ManyToManyField(Service, related_name='packages')
    is_active = models.BooleanField(default=True)
    grants_vip_months = models.PositiveIntegerField(
        default=0,
        help_text="Number of free VIP months granted upon purchase."
    )

    def __str__(self):
        return self.name


class Payment(BaseModel):
    """
    Represents a payment transaction, linking to an appointment or order.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESSFUL = 'SUCCESSFUL', 'Successful'
        FAILED = 'FAILED', 'Failed'
        
    class PaymentType(models.TextChoices):
        ADVANCE = 'ADVANCE', 'Anticipo'
        FINAL = 'FINAL', 'Pago Final'
        FULL = 'FULL', 'Pago Completo'

    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.SET_NULL, null=True)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    transaction_id = models.CharField(
        max_length=255, unique=True, help_text="ID from the payment gateway (e.g., Wompi)")
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.FULL)

    def __str__(self):
        return f"Payment {self.transaction_id} for {self.amount} ({self.status})"