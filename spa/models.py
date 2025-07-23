# spa/models.py

from django.db import models
from django.conf import settings
from core.models import BaseModel
import uuid
from django.utils import timezone # Importar timezone para la fecha de expiración

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
    class AppointmentStatus(models.TextChoices):
        PENDING_ADVANCE = 'PENDING_ADVANCE', 'Pendiente de Pago de Anticipo'
        CONFIRMED = 'CONFIRMED', 'Confirmada (Anticipo Pagado)'
        COMPLETED_PENDING_FINAL_PAYMENT = 'COMPLETED_PENDING_FINAL_PAYMENT', 'Completada (Pago Final Pendiente)'
        COMPLETED = 'COMPLETED', 'Completada y Pagada'
        CANCELLED_BY_CLIENT = 'CANCELLED_BY_CLIENT', 'Cancelada por el Cliente'
        CANCELLED_BY_SYSTEM = 'CANCELLED_BY_SYSTEM', 'Cancelada por el Sistema'
        CANCELLED_BY_ADMIN = 'CANCELLED_BY_ADMIN', 'Cancelada por el Administrador'
        REDEEMED_WITH_VOUCHER = 'REDEEMED_WITH_VOUCHER', 'Redimida con Voucher' # Nuevo estado

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
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name='appointments')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    status = models.CharField(
        max_length=40,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.PENDING_ADVANCE
    )
    
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, help_text="Final price for the service. Can be 0 if paid with a voucher.")
    
    reschedule_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this appointment has been rescheduled by the client."
    )

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ['-start_time']

    def __str__(self):
        return f"Appointment for {self.user} with {self.staff_member or 'N/A'} at {self.start_time.strftime('%Y-%m-%d %H:%M')}"


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
        # --- INICIO DE LA MODIFICACIÓN ---
        # Nuevo estado para pagos cubiertos por crédito
        PAID_WITH_CREDIT = 'PAID_WITH_CREDIT', 'Pagado con Saldo a Favor'
        # --- FIN DE LA MODIFICACIÓN ---

    class PaymentType(models.TextChoices):
        ADVANCE = 'ADVANCE', 'Anticipo de Cita'
        FINAL = 'FINAL', 'Pago Final de Cita'
        PACKAGE = 'PACKAGE', 'Compra de Paquete'
        VIP_SUBSCRIPTION = 'VIP_SUBSCRIPTION', 'Suscripción VIP'

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
        return (
            self.status == self.VoucherStatus.AVAILABLE and
            self.user_package.expires_at >= timezone.now().date()
        )

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
        related_name='generated_credit'
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
