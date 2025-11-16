# spa/models.py

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone  # Importar timezone para la fecha de expiración
from simple_history.models import HistoricalRecords

from core.models import BaseModel
import uuid

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
    history = HistoricalRecords(inherit=True)

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

    def clean(self):
        super().clean()
        if self.start_time >= self.end_time:
            raise ValidationError({"start_time": "La hora de inicio debe ser menor a la hora de fin."})
        if not self.staff_member_id or self.day_of_week is None:
            return
        overlap_exists = (
            StaffAvailability.objects.filter(
                staff_member=self.staff_member,
                day_of_week=self.day_of_week,
            )
            .exclude(id=self.id)
            .filter(
                Q(start_time__lt=self.end_time) &
                Q(end_time__gt=self.start_time)
            )
            .exists()
        )
        if overlap_exists:
            raise ValidationError({
                "start_time": "El horario se solapa con otro bloque existente.",
                "end_time": "El horario se solapa con otro bloque existente.",
            })


class AvailabilityExclusion(BaseModel):
    """
    Representa bloqueos temporales o recurrentes (almuerzos/ausencias) en la agenda.
    """
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
    """
    Represents a booking of one or multiple services by a user with a staff member.
    """

    class AppointmentStatus(models.TextChoices):
        PENDING_ADVANCE = 'PENDING_ADVANCE', 'Pendiente de Pago de Anticipo'
        CONFIRMED = 'CONFIRMED', 'Confirmada (Anticipo Pagado)'
        COMPLETED_PENDING_FINAL_PAYMENT = 'COMPLETED_PENDING_FINAL_PAYMENT', 'Completada (Pago Final Pendiente)'
        COMPLETED = 'COMPLETED', 'Completada y Pagada'
        CANCELLED_BY_CLIENT = 'CANCELLED_BY_CLIENT', 'Cancelada por el Cliente'
        CANCELLED_BY_SYSTEM = 'CANCELLED_BY_SYSTEM', 'Cancelada por el Sistema'
        CANCELLED_BY_ADMIN = 'CANCELLED_BY_ADMIN', 'Cancelada por el Administrador'
        REDEEMED_WITH_VOUCHER = 'REDEEMED_WITH_VOUCHER', 'Redimida con Voucher'
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
        default=AppointmentStatus.PENDING_ADVANCE
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

    class Meta:
        verbose_name = "Appointment Item"
        verbose_name_plural = "Appointment Items"

    def __str__(self):
        return f"{self.service.name} ({self.duration} min)"


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


class Package(BaseModel):
    """
    Represents a bundle of services that can be purchased together.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Cambiamos a ManyToManyField para especificar cuántas sesiones de cada servicio incluye
    services = models.ManyToManyField(Service, through='PackageService', related_name='packages')
    is_active = models.BooleanField(default=True)
    grants_vip_months = models.PositiveIntegerField(
        default=0,
        help_text="Number of free VIP months granted upon purchase."
    )
    # Nuevo campo para definir la validez de los vouchers generados
    validity_days = models.PositiveIntegerField(default=90, help_text="Number of days the vouchers from this package are valid after purchase.")


    def __str__(self):
        return self.name

class PackageService(BaseModel):
    """
    Tabla intermedia para especificar la cantidad de sesiones
    de un servicio dentro de un paquete.
    """
    package = models.ForeignKey(Package, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('package', 'service')

    def __str__(self):
        return f"{self.quantity} x {self.service.name} in {self.package.name}"

class Payment(BaseModel):
    # ... (Se añaden campos para relacionar con ClientCredit)
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        APPROVED = 'APPROVED', 'Aprobado'
        DECLINED = 'DECLINED', 'Declinado'
        ERROR = 'ERROR', 'Error'
        TIMEOUT = 'TIMEOUT', 'Sin confirmación'
        # --- INICIO DE LA MODIFICACIÓN ---
        # Nuevo estado para pagos cubiertos por crédito
        PAID_WITH_CREDIT = 'PAID_WITH_CREDIT', 'Pagado con Saldo a Favor'
        # --- FIN DE LA MODIFICACIÓN ---

    class PaymentType(models.TextChoices):
        ADVANCE = 'ADVANCE', 'Anticipo de Cita'
        FINAL = 'FINAL', 'Pago Final de Cita'
        PACKAGE = 'PACKAGE', 'Compra de Paquete'
        VIP_SUBSCRIPTION = 'VIP_SUBSCRIPTION', 'Suscripción VIP'
        TIP = 'TIP', 'Propina'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True
    )
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    transaction_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True, help_text="ID from the payment gateway (e.g., Wompi)")
    payment_type = models.CharField(max_length=16, choices=PaymentType.choices)
    raw_response = models.JSONField(null=True, blank=True)

    # --- INICIO DE LA MODIFICACIÓN ---
    # Campo para registrar qué crédito se usó para este pago
    used_credit = models.ForeignKey(
        'ClientCredit',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_covered',
        help_text="Crédito de cliente que se utilizó para cubrir este pago."
    )
    # --- FIN DE LA MODIFICACIÓN ---

    def __str__(self):
        return f"Payment {self.id} for {self.amount} ({self.status})"

def generate_voucher_code():
    """Generates a unique, short voucher code."""
    return uuid.uuid4().hex[:8].upper()

class UserPackage(BaseModel):
    """
    Tracks the purchase of a service package by a user. This is the 'master' record
    that owns the vouchers.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchased_packages')
    package = models.ForeignKey(Package, on_delete=models.PROTECT, related_name='purchases')
    purchase_date = models.DateTimeField(default=timezone.now)
    # Un UserPackage ahora se relaciona directamente con UN pago.
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='user_package_purchase', null=True, blank=True)
    expires_at = models.DateField(default=timezone.now, help_text="Date when the vouchers from this package expire.")

    class Meta:
        verbose_name = "User's Purchased Package"
        verbose_name_plural = "User's Purchased Packages"
        ordering = ['-purchase_date']

    def __str__(self):
        return f"Package '{self.package.name}' purchased by {self.user.get_full_name()}"
    
    def save(self, *args, **kwargs):
        # Calcular la fecha de expiración al guardar por primera vez
        if not self.pk and self.package.validity_days:
            self.expires_at = self.purchase_date.date() + timezone.timedelta(days=self.package.validity_days)
        super().save(*args, **kwargs)


class Voucher(BaseModel):
    """
    Represents a single, redeemable service credit for a user,
    generated from a UserPackage purchase.
    """
    class VoucherStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Disponible'
        REDEEMED = 'REDEEMED', 'Redimido'
        EXPIRED = 'EXPIRED', 'Expirado'

    code = models.CharField(max_length=8, default=generate_voucher_code, unique=True, editable=False)
    user_package = models.ForeignKey(UserPackage, on_delete=models.CASCADE, related_name='vouchers', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vouchers')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='vouchers')
    status = models.CharField(max_length=10, choices=VoucherStatus.choices, default=VoucherStatus.AVAILABLE)
    expires_at = models.DateField(null=True, blank=True)
    
    # El appointment donde se canjeó este voucher
    redeemed_appointment = models.OneToOneField(
        Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='used_voucher'
    )

    class Meta:
        verbose_name = "Service Voucher"
        verbose_name_plural = "Service Vouchers"
        ordering = ['-created_at']

    def __str__(self):
        return f"Voucher {self.code} for '{self.service.name}' ({self.user.get_full_name()}) - {self.status}"
    
    @property
    def is_redeemable(self):
        """Checks if the voucher can be used."""
        valid_until = self.expires_at
        if not valid_until and self.user_package:
            valid_until = self.user_package.expires_at
        return self.status == self.VoucherStatus.AVAILABLE and (not valid_until or valid_until >= timezone.now().date())

    def save(self, *args, **kwargs):
        from core.models import AuditLog
        previous_status = None
        if self.pk:
            previous_status = Voucher.objects.filter(pk=self.pk).values_list('status', flat=True).first()
        if not self.expires_at and self.user_package:
            self.expires_at = self.user_package.expires_at
        super().save(*args, **kwargs)
        if previous_status and previous_status != self.status and self.status == self.VoucherStatus.REDEEMED:
            AuditLog.objects.create(
                admin_user=None,
                target_user=self.user,
                target_appointment=self.redeemed_appointment,
                action=AuditLog.Action.VOUCHER_REDEEMED,
                details=f"Voucher {self.code} redimido por {self.user_id}",
            )


class WebhookEvent(BaseModel):
    class Status(models.TextChoices):
        PROCESSED = 'PROCESSED', 'Procesado'
        FAILED = 'FAILED', 'Fallido'
        IGNORED = 'IGNORED', 'Ignorado'

    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)
    event_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSED)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Evento de Webhook"
        verbose_name_plural = "Eventos de Webhook"
        ordering = ['-created_at']


class LoyaltyRewardLog(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='loyalty_rewards',
    )
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loyalty_reward',
    )
    rewarded_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "Recompensa de Lealtad"
        verbose_name_plural = "Recompensas de Lealtad"
        ordering = ['-rewarded_at']

class SubscriptionLog(BaseModel):
    """
    Registra cada pago de suscripción VIP para un usuario, manteniendo
    un historial claro de su membresía.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='subscription_logs'
    )
    payment = models.OneToOneField(
        Payment, on_delete=models.PROTECT, related_name='subscription_log'
    )
    start_date = models.DateField(help_text="Fecha de inicio del período de la membresía.")
    end_date = models.DateField(help_text="Fecha de finalización del período de la membresía.")

    class Meta:
        verbose_name = "Registro de Suscripción"
        verbose_name_plural = "Registros de Suscripciones"
        ordering = ['-start_date']

    def __str__(self):
        return f"Suscripción para {self.user.first_name} válida hasta {self.end_date.strftime('%Y-%m-%d')}"

class ClientCredit(BaseModel):
    """
    Representa un saldo a favor que un cliente puede usar en futuras compras.
    Se genera a partir del anticipo de una cita cancelada.
    """
    class CreditStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Disponible'
        PARTIALLY_USED = 'PARTIALLY_USED', 'Parcialmente Usado'
        FULLY_USED = 'FULLY_USED', 'Totalmente Usado'
        EXPIRED = 'EXPIRED', 'Expirado'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credits'
    )
    # El pago original que generó este crédito (el anticipo de la cita cancelada)
    originating_payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name='generated_credit',
        null=True,
        blank=True,
    )
    initial_amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=CreditStatus.choices,
        default=CreditStatus.AVAILABLE
    )
    expires_at = models.DateField()

    class Meta:
        verbose_name = "Saldo a Favor de Cliente"
        verbose_name_plural = "Saldos a Favor de Clientes"
        ordering = ['-created_at']

    def __str__(self):
        return f"Crédito de {self.remaining_amount} para {self.user.get_full_name()} (Expira: {self.expires_at})"

    def save(self, *args, **kwargs):
        # Lógica para actualizar el estado automáticamente
        if self.remaining_amount <= 0:
            self.status = self.CreditStatus.FULLY_USED
            self.remaining_amount = 0 # Asegurar que no sea negativo
        elif self.remaining_amount < self.initial_amount:
            self.status = self.CreditStatus.PARTIALLY_USED
        else:
            self.status = self.CreditStatus.AVAILABLE
            
        super().save(*args, **kwargs)


class FinancialAdjustment(BaseModel):
    class AdjustmentType(models.TextChoices):
        CREDIT = 'CREDIT', 'Nota Crédito'
        DEBIT = 'DEBIT', 'Nota Débito'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='financial_adjustments',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    adjustment_type = models.CharField(max_length=6, choices=AdjustmentType.choices)
    reason = models.TextField()
    related_payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='financial_adjustments',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='financial_adjustments_created',
    )

    class Meta:
        verbose_name = "Ajuste Financiero"
        verbose_name_plural = "Ajustes Financieros"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.adjustment_type} {self.amount} para {self.user}"
