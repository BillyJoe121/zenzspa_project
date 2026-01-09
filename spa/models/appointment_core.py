from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.utils.exceptions import BusinessLogicError
from core.models import BaseModel
from .services import Service


class Appointment(BaseModel):
    class AppointmentStatus(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pendiente de Pago"
        CONFIRMED = "CONFIRMED", "Confirmada"
        FULLY_PAID = "FULLY_PAID", "Totalmente Pagado"
        RESCHEDULED = "RESCHEDULED", "Reagendada"
        COMPLETED = "COMPLETED", "Completada"
        CANCELLED = "CANCELLED", "Cancelada"

    class AppointmentOutcome(models.TextChoices):
        NONE = "NONE", "Sin resultado"
        CANCELLED_BY_CLIENT = "CANCELLED_BY_CLIENT", "Cancelada por el Cliente"
        CANCELLED_BY_SYSTEM = "CANCELLED_BY_SYSTEM", "Cancelada por el Sistema"
        CANCELLED_BY_ADMIN = "CANCELLED_BY_ADMIN", "Cancelada por el Administrador"
        NO_SHOW = "NO_SHOW", "No Asistió"
        REFUNDED = "REFUNDED", "Reembolsada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments")
    staff_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attended_appointments",
        limit_choices_to={"role__in": ["STAFF", "ADMIN"]},
        null=True,
        blank=True,
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    services = models.ManyToManyField(Service, through="AppointmentItem", related_name="appointments")
    status = models.CharField(max_length=40, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING_PAYMENT)
    outcome = models.CharField(
        max_length=40,
        choices=AppointmentOutcome.choices,
        default=AppointmentOutcome.NONE,
    )
    price_at_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Final price for all the services booked in this appointment.",
    )
    reschedule_count = models.PositiveIntegerField(default=0, help_text="How many times this appointment has been rescheduled by the client.")

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["start_time", "status"], name="appt_time_status_idx"),
            models.Index(fields=["staff_member", "start_time"], name="appt_staff_time_idx"),
            models.Index(fields=["status", "start_time"], name="appt_status_time_idx"),
            models.Index(fields=["user", "start_time"], name="appt_user_time_idx"),
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
        return ", ".join(item.service.name for item in self.items.select_related("service"))

    # ACTION PERMISSIONS
    def can_reschedule(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "No puedes reagendar una cita cancelada o completada"
        if self.start_time < timezone.now():
            return False, "No puedes reagendar una cita que ya pasó"
        if self.status not in [
            self.AppointmentStatus.PENDING_PAYMENT,
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]:
            return False, "La cita debe estar confirmada para poder reagendarla"
        if user.role == CustomUser.Role.CLIENT and self.reschedule_count >= 3:
            return False, "Has alcanzado el límite de 3 reagendamientos para esta cita"
        return True, ""

    def can_cancel(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "La cita ya está cancelada o completada"
        if user.role == CustomUser.Role.CLIENT:
            if self.status in [
                self.AppointmentStatus.CONFIRMED,
                self.AppointmentStatus.RESCHEDULED,
                self.AppointmentStatus.FULLY_PAID,
            ]:
                hours_until = (self.start_time - timezone.now()).total_seconds() / 3600
                if hours_until < 24:
                    return False, "Esta cita ya fue pagada. Debes usar la opción de reagendar (menos de 24h de anticipación)"
        return True, ""

    def can_mark_completed(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede marcar citas como completadas"
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]:
            return False, "Solo las citas confirmadas pueden marcarse como completadas"
        if self.start_time > timezone.now():
            return False, "No puedes marcar como completada una cita que aún no ha ocurrido"
        return True, ""

    def can_mark_no_show(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede marcar no-show"
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]:
            return False, "Solo las citas confirmadas pueden marcarse como no-show"
        if self.start_time > timezone.now():
            return False, "No se puede marcar como no-show una cita que aún no ha ocurrido"
        return True, ""

    def can_complete_final_payment(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return False, "Solo el personal puede procesar pagos"
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]:
            return False, "La cita debe estar confirmada para procesar el pago final"
        return True, ""

    def can_add_tip(self, user) -> tuple[bool, str]:
        if self.status in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
            self.AppointmentStatus.COMPLETED,
        ]:
            return True, ""
        return False, "Solo puedes agregar propinas a citas confirmadas o completadas"

    def can_download_ical(self, user) -> tuple[bool, str]:
        if self.status not in [
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]:
            return False, "Solo puedes exportar citas confirmadas"
        if self.start_time < timezone.now():
            return False, "No tiene sentido exportar una cita que ya pasó"
        return True, ""

    def can_cancel_by_admin(self, user) -> tuple[bool, str]:
        from users.models import CustomUser

        if user.role != CustomUser.Role.ADMIN:
            return False, "Solo administradores pueden usar esta acción"
        if self.status in [self.AppointmentStatus.CANCELLED, self.AppointmentStatus.COMPLETED]:
            return False, "No puedes cancelar una cita que ya está cancelada o completada"
        return True, ""

    @property
    def is_active(self):
        return self.status in [
            self.AppointmentStatus.PENDING_PAYMENT,
            self.AppointmentStatus.CONFIRMED,
            self.AppointmentStatus.RESCHEDULED,
            self.AppointmentStatus.FULLY_PAID,
        ]

    @property
    def is_past(self):
        return self.start_time < timezone.now()

    @property
    def is_upcoming(self):
        return self.start_time > timezone.now()

    @property
    def hours_until_appointment(self):
        return (self.start_time - timezone.now()).total_seconds() / 3600

    @property
    def outstanding_balance(self):
        from decimal import Decimal
        from django.db.models import Sum
        from finances.models import Payment

        paid_amount = Payment.objects.filter(
            appointment=self,
            status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT],
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        outstanding = self.price_at_purchase - paid_amount
        return max(outstanding, Decimal("0.00"))


class AppointmentItemManager(models.Manager):
    def _apply_defaults(self, obj):
        if obj.duration is None and obj.service:
            obj.duration = obj.service.duration
        if obj.price_at_purchase is None and obj.service:
            try:
                from users.models import CustomUser

                is_vip = getattr(obj.appointment, "user", None) and getattr(obj.appointment.user, "role", None) == CustomUser.Role.VIP
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
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="appointment_items")
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
            exists = AppointmentItem.objects.filter(appointment=self.appointment, service=self.service).exclude(id=self.id).exists()
            if exists:
                raise ValidationError({"service": f"El servicio '{self.service.name}' ya está incluido en esta cita."})

            if self.appointment and self.duration:
                other_items_duration = (
                    AppointmentItem.objects.filter(appointment=self.appointment).exclude(id=self.id).aggregate(total=models.Sum("duration"))["total"]
                    or 0
                )
                total_duration = other_items_duration + self.duration
                appointment_duration = (self.appointment.end_time - self.appointment.start_time).total_seconds() / 60

                if total_duration > appointment_duration:
                    raise ValidationError(
                        {
                            "duration": f"La duración total de servicios ({total_duration} min) "
                            f"excede el tiempo de la cita ({int(appointment_duration)} min)."
                        }
                    )
