from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel
from spa.models import Appointment, Voucher

from .catalog import ProductVariant

class Order(BaseModel):
    class OrderStatus(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pendiente de Pago'
        PAID = 'PAID', 'Pagada'
        PREPARING = 'PREPARING', 'En Preparación'
        SHIPPED = 'SHIPPED', 'Enviada'
        DELIVERED = 'DELIVERED', 'Entregada'
        CANCELLED = 'CANCELLED', 'Cancelada'
        RETURN_REQUESTED = 'RETURN_REQUESTED', 'Devolución Solicitada'
        RETURN_APPROVED = 'RETURN_APPROVED', 'Devolución Aprobada'
        RETURN_REJECTED = 'RETURN_REJECTED', 'Devolución Rechazada'
        REFUNDED = 'REFUNDED', 'Reembolsada'
        FRAUD_ALERT = 'FRAUD_ALERT', 'Alerta de Fraude'

    class DeliveryOptions(models.TextChoices):
        PICKUP = 'PICKUP', 'Recogida en Local'
        DELIVERY = 'DELIVERY', 'Envío a Domicilio'
        ASSOCIATE_TO_APPOINTMENT = 'ASSOCIATE_TO_APPOINTMENT', 'Asociar a Cita Futura'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name="Usuario"
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
        verbose_name="Estado de la Orden"
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Monto Total"
    )
    delivery_option = models.CharField(
        max_length=30,
        choices=DeliveryOptions.choices,
        verbose_name="Opción de Entrega"
    )
    delivery_address = models.TextField(
        blank=True, null=True,
        verbose_name="Dirección de Envío"
    )
    shipping_cost = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        verbose_name="Costo de Envío",
        help_text="Costo de envío aplicado a esta orden"
    )
    associated_appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Cita Asociada"
    )
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Número de Seguimiento"
    )
    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    shipping_date = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha de Envío"
    )
    estimated_delivery_date = models.DateField(
        null=True, blank=True,
        verbose_name="Fecha Estimada de Entrega"
    )
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Voucher Utilizado"
    )
    wompi_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID Transacción Wompi"
    )
    return_reason = models.TextField(blank=True, verbose_name="Motivo de devolución")
    return_requested_at = models.DateTimeField(null=True, blank=True)
    return_request_data = models.JSONField(default=list, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    fraud_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Orden"
        verbose_name_plural = "Órdenes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Orden {self.id} - {self.user.email}"

    def clean(self):
        super().clean()
        if self.delivery_option == self.DeliveryOptions.DELIVERY:
            if not self.delivery_address or len(self.delivery_address.strip()) < 15:
                raise ValidationError({
                    "delivery_address": "La dirección de envío es obligatoria y debe tener al menos 15 caracteres."
                })

            # Validación de nomenclatura colombiana
            import re
            address_lower = self.delivery_address.lower()

            # Debe incluir tipo de vía
            via_types = [
                'calle', 'carrera', 'avenida', 'transversal', 'diagonal',
                'circular', 'autopista', 'manzana', 'vereda', 'kilometro',
                'cra', 'cll', 'av', 'trans', 'diag', 'circ', 'km'
            ]

            if not any(via_type in address_lower for via_type in via_types):
                raise ValidationError({
                    "delivery_address": "La dirección debe incluir el tipo de vía (Calle, Carrera, Avenida, etc.)."
                })

            # Debe tener formato de nomenclatura colombiana
            nomenclatura_pattern = r'\d+\s*[#]\s*\d+[\s\-]\d+'
            if not re.search(nomenclatura_pattern, self.delivery_address):
                raise ValidationError({
                    "delivery_address": "La dirección debe seguir el formato de nomenclatura colombiana (ej: Calle 123 #45-67)."
                })

class OrderItem(BaseModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Orden"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name="Variante"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    price_at_purchase = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Precio al Comprar"
    )
    quantity_returned = models.PositiveIntegerField(
        default=0,
        verbose_name="Cantidad Devuelta"
    )

    class Meta:
        verbose_name = "Ítem de Orden"
        verbose_name_plural = "Ítems de Órdenes"

    def __str__(self):
        return f"{self.quantity} x {self.variant}"

    def clean(self):
        if self.quantity_returned > self.quantity:
            raise ValidationError("La cantidad devuelta no puede ser mayor que la comprada")

