from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from .appointment import Service


class Package(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    services = models.ManyToManyField(Service, through='PackageService', related_name='packages')
    is_active = models.BooleanField(default=True)
    grants_vip_months = models.PositiveIntegerField(
        default=0,
        help_text="Number of free VIP months granted upon purchase."
    )
    validity_days = models.PositiveIntegerField(default=90, help_text="Number of days the vouchers from this package are valid after purchase.")

    def __str__(self):
        return self.name


class PackageService(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('package', 'service')

    def __str__(self):
        return f"{self.quantity} x {self.service.name} in {self.package.name}"


class VoucherCodeGenerator:
    @staticmethod
    def generate_code():
        import uuid
        return uuid.uuid4().hex[:10].upper()

def generate_voucher_code():
    return VoucherCodeGenerator.generate_code()

class Voucher(BaseModel):
    class VoucherStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Disponible'
        USED = 'USED', 'Usado'
        EXPIRED = 'EXPIRED', 'Expirado'

    user_package = models.ForeignKey(
        'UserPackage',
        on_delete=models.CASCADE,
        related_name='vouchers',
        null=True,
        blank=True,
        help_text="Paquete de origen del voucher."
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vouchers'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='vouchers'
    )
    code = models.CharField(max_length=50, unique=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=VoucherStatus.choices,
        default=VoucherStatus.AVAILABLE,
    )
    expires_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['expires_at']

    def __str__(self):
        return f"{self.code} ({self.service.name})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_voucher_code()
        if self.user_package and not self.expires_at:
            validity_days = self.user_package.package.validity_days if self.user_package.package else 90
            from django.utils import timezone
            self.expires_at = timezone.now().date() + timezone.timedelta(days=validity_days)
        super().save(*args, **kwargs)


class UserPackage(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_packages'
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name='user_packages'
    )
    purchase_date = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateField(
        help_text="Fecha en la que expiran los vouchers de este paquete.",
    )

    def __str__(self):
        return f"{self.user} - {self.package}"

    def save(self, *args, **kwargs):
        if not self.purchase_date:
            self.purchase_date = timezone.now()
        if not self.expires_at:
            validity_days = getattr(self.package, "validity_days", 0) or 0
            self.expires_at = self.purchase_date.date() + timezone.timedelta(days=validity_days)
        super().save(*args, **kwargs)
