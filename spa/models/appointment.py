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
    what_is_included = models.TextField(
        blank=True,
        help_text="Detalle de qué incluye el servicio (pasos, productos, etc.)"
    )
    benefits = models.TextField(
        blank=True,
        help_text="Beneficios para la piel (e.g. hidratación, luminosidad)"
    )
    contraindications = models.TextField(
        blank=True,
        help_text="Contraindicaciones médicas o de salud."
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
        CONFIRMED = 'CONFIRMED', 'Confirmada'
        FULLY_PAID = 'FULLY_PAID', 'Totalmente Pagado'
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
        # Índices para optimizar queries de analytics
        indexes = [
            models.Index(fields=['start_time', 'status'], name='appt_time_status_idx'),
            models.Index(fields=['staff_member', 'start_time'], name='appt_staff_time_idx'),
            models.Index(fields=['status', 'start_time'], name='appt_status_time_idx'),
            models.Index(fields=['user', 'start_time'], name='appt_user_time_idx'),
        ]

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

    # ========================================
    # ACTION PERMISSION METHODS
    # ========================================
    # These methods centralize the business logic for determining
    # which actions are available for an appointment based on its
    # current state, payment status, and user role.
    # Returns: (can_perform: bool, reason: str)

    def can_reschedule(self, user) -> tuple[bool, str]:
        """
        Determines if an appointment can be rescheduled.

        Rules:
        - Cannot reschedule cancelled or completed appointments
        - Cannot reschedule appointments in the past
        - Clients have a limit of 3 reschedulesules
        - Clients must have paid advance to reschedule (or be in CONFIRMED/RESCHEDULED status)
        - Admins/Staff bypass most restrictions
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Cannot reschedule if cancelled or completed
        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "No puedes reagendar una cita cancelada o completada"

        # Rule 2: Cannot reschedule appointments in the past
        if self.start_time < timezone.now():
            return False, "No puedes reagendar una cita que ya pasó"

        # Rule 3: Must be in a reschedulable state
        if self.status not in [
            self.AppointmentStatus.PENDING_PAYMENT,
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]:
            return False, "La cita debe estar confirmada para poder reagendarla"

        # Rule 4: Client-specific restrictions
        if user.role == CustomUser.Role.CLIENT:
            # Max 3 reschedules for clients
            if self.reschedule_count >= 3:
                return False, "Has alcanzado el límite de 3 reagendamientos para esta cita"

        return True, ""

    def can_cancel(self, user) -> tuple[bool, str]:
        """
        Determines if an appointment can be cancelled.

        Rules:
        - Cannot cancel if already cancelled or completed
        - Clients cannot cancel with < 24h if advance was paid (must reschedule instead)
        - Admins/Staff can always cancel
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Cannot cancel if already in terminal state
        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "La cita ya está cancelada o completada"

        # Rule 2: Client-specific 24h rule for paid appointments
        if user.role == CustomUser.Role.CLIENT:
            # If appointment is confirmed/rescheduled/fully_paid (advance was paid)
            if self.status in [
                self.AppointmentStatus.CONFIRMED,
                self.AppointmentStatus.RESCHEDULED,
                self.AppointmentStatus.FULLY_PAID
            ]:
                hours_until = (self.start_time - timezone.now()).total_seconds() / 3600
                if hours_until < 24:
                    return False, "Esta cita ya fue pagada. Debes usar la opción de reagendar (menos de 24h de anticipación)"

        return True, ""

    def can_mark_completed(self, user) -> tuple[bool, str]:
        """
        Determines if staff can mark an appointment as completed.

        Rules:
        - Only staff/admin can mark as completed
        - Appointment must be confirmed, rescheduled, or paid
        - Appointment cannot be in the future
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Only staff/admin
        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede marcar citas como completadas"

        # Rule 2: Must be in completable state
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]:
            return False, "Solo las citas confirmadas pueden marcarse como completadas"

        # Rule 3: Cannot complete future appointments
        if self.start_time > timezone.now():
            return False, "No puedes marcar como completada una cita que aún no ha ocurrido"

        return True, ""

    def can_mark_no_show(self, user) -> tuple[bool, str]:
        """
        Determines if staff can mark an appointment as no-show.

        Rules:
        - Only staff/admin can mark no-show
        - Appointment must be confirmed, rescheduled, or fully paid
        - Appointment must be in the past
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Only staff/admin
        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede marcar no-show"

        # Rule 2: Must be in a confirmed state
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]:
            return False, "Solo las citas confirmadas pueden marcarse como no-show"

        # Rule 3: Must be in the past
        if self.start_time > timezone.now():
            return False, "No se puede marcar como no-show una cita que aún no ha ocurrido"

        return True, ""

    def can_complete_final_payment(self, user) -> tuple[bool, str]:
        """
        Determines if staff can process final payment.

        Rules:
        - Only staff/admin can process payments
        - Appointment must be confirmed, rescheduled, or paid
        - Cannot process if already fully paid (status COMPLETED typically means fully paid)
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Only staff/admin
        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede procesar pagos"

        # Rule 2: Must be in payable state
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]:
            return False, "La cita debe estar confirmada para procesar el pago final"

        # Note: We don't check if already fully paid here because that's a payment system concern
        # The payment service will handle that validation

        return True, ""

    def can_add_tip(self, user) -> tuple[bool, str]:
        """
        Determines if a tip can be added.

        Rules:
        - Tips can be added to any confirmed, paid, or completed appointment
        - No specific time restrictions
        """
        # Tips are flexible - can be added anytime for active or completed appointments
        if self.status in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
            self.AppointmentStatus.COMPLETED
        ]:
            return True, ""

        return False, "Solo puedes agregar propinas a citas confirmadas o completadas"

    def can_download_ical(self, user) -> tuple[bool, str]:
        """
        Determines if appointment can be exported to calendar.

        Rules:
        - Only for confirmed, rescheduled, or paid appointments
        - Only for future appointments (past appointments don't make sense in calendar)
        """
        # Rule 1: Must be in active state
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]:
            return False, "Solo puedes exportar citas confirmadas"

        # Rule 2: Should be a future appointment
        if self.start_time < timezone.now():
            return False, "No tiene sentido exportar una cita que ya pasó"

        return True, ""

    def can_cancel_by_admin(self, user) -> tuple[bool, str]:
        """
        Determines if admin can cancel appointment.

        Rules:
        - Only admin can use this action
        - Cannot cancel already cancelled or completed appointments
        """
        # Avoid circular import
        from users.models import CustomUser

        # Rule 1: Only admin
        if user.role != CustomUser.Role.ADMIN:
            return False, "Solo administradores pueden usar esta acción"

        # Rule 2: Cannot cancel terminal states
        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "No puedes cancelar una cita que ya está cancelada o completada"

        return True, ""

    # ========================================
    # HELPER PROPERTIES
    # ========================================

    @property
    def is_active(self):
        """Returns True if appointment is in an active state (can be modified)."""
        return self.status in [
            self.AppointmentStatus.PENDING_PAYMENT,
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID
        ]

    @property
    def is_past(self):
        """Returns True if appointment start time is in the past."""
        return self.start_time < timezone.now()

    @property
    def is_upcoming(self):
        """Returns True if appointment is in the future."""
        return self.start_time > timezone.now()

    @property
    def hours_until_appointment(self):
        """Returns hours until appointment (negative if past)."""
        return (self.start_time - timezone.now()).total_seconds() / 3600

    @property
    def outstanding_balance(self):
        """
        Calcula el saldo pendiente de pago para esta cita.

        Returns:
            Decimal: Monto pendiente (price_at_purchase - total_paid)
        """
        from finances.models import Payment
        from decimal import Decimal
        from django.db.models import Sum

        # Sumar todos los pagos aprobados
        paid_amount = Payment.objects.filter(
            appointment=self,
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT
            ]
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        # Calcular pendiente
        outstanding = self.price_at_purchase - paid_amount
        return max(outstanding, Decimal('0.00'))


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
        """
        Validaciones de dominio para AppointmentItem.

        Valida:
        1. Servicios duplicados en la misma cita
        2. Solapamiento temporal con otros items de la misma cita
        3. Que el item cabe dentro del tiempo total de la cita
        """
        super().clean()
        if self.appointment_id and self.service_id:
            # 1. Check if service already exists in this appointment (exclude self)
            exists = AppointmentItem.objects.filter(
                appointment=self.appointment,
                service=self.service
            ).exclude(id=self.id).exists()
            if exists:
                raise ValidationError({
                    'service': f"El servicio '{self.service.name}' ya está incluido en esta cita."
                })

            # 2. Validar que la duración total de items no exceda el tiempo de la cita
            if self.appointment and self.duration:
                # Obtener duración total de otros items
                other_items_duration = AppointmentItem.objects.filter(
                    appointment=self.appointment
                ).exclude(id=self.id).aggregate(
                    total=models.Sum('duration')
                )['total'] or 0

                # Calcular duración total incluyendo este item
                total_duration = other_items_duration + self.duration

                # Calcular tiempo disponible en la cita
                appointment_duration = (
                    self.appointment.end_time - self.appointment.start_time
                ).total_seconds() / 60  # Convertir a minutos

                if total_duration > appointment_duration:
                    raise ValidationError({
                        'duration': f"La duración total de servicios ({total_duration} min) "
                                  f"excede el tiempo de la cita ({int(appointment_duration)} min)."
                    })


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
