"""
KPI Financials - Métricas financieras y de ventas.
"""
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from finances.models import Payment
from marketplace.models import Order
from users.models import CustomUser
from analytics.decorators import log_performance


class FinancialMetricsMixin:
    """Métricas financieras y de ventas."""

    def _get_ltv_by_role(self):
        """
        Calcula LTV (Lifetime Value) promedio por rol.
        Retorna un dict: {role: {'total_amount': X, 'user_count': Y, 'ltv': Z}}
        """
        filters = Q(
            payments__created_at__date__gte=self.start_date,
            payments__created_at__date__lte=self.end_date,
            payments__status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ]
        ) & ~Q(payments__payment_type__in=self._excluded_payment_types())

        data = (
            CustomUser.objects
            .values('role')
            .annotate(
                total_amount=Coalesce(Sum('payments__amount', filter=filters), Decimal("0")),
                user_count=Count('id', filter=filters, distinct=True)
            )
            .filter(total_amount__gt=0)
        )

        result = {}
        for entry in data:
            role = entry['role']
            total = entry['total_amount']
            count = entry['user_count']
            if count > 0:
                result[role] = {
                    'total_spent': float(total),
                    'user_count': count,
                    'ltv': float(total / count)
                }
        return result

    def _get_average_order_value(self):
        """
        Average Order Value = suma(total_amount) ÷ número de órdenes emitidas en el periodo.
        """
        avg = self._order_queryset().aggregate(avg=Avg("total_amount"))["avg"]
        return float(avg or Decimal("0"))

    def _get_debt_recovery_metrics(self):
        """
        Tasa de Recuperación = monto recuperado de pagos inicialmente en mora ÷ deuda generada.
        """
        base_qs = Payment.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        )
        debt_statuses = [
            Payment.PaymentStatus.PENDING,
            Payment.PaymentStatus.DECLINED,
            Payment.PaymentStatus.ERROR,
            Payment.PaymentStatus.TIMEOUT,
        ]
        total_generated = base_qs.filter(status__in=debt_statuses).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0"))
        )["total"]
        recovered_amount = base_qs.filter(
            status=Payment.PaymentStatus.APPROVED,
            updated_at__date__gte=self.start_date,
            updated_at__date__lte=self.end_date,
        ).exclude(created_at=F("updated_at")).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0"))
        )["total"]
        total_generated = total_generated or Decimal("0")
        recovered_amount = recovered_amount or Decimal("0")
        rate = float(recovered_amount /
                     total_generated) if total_generated > 0 else 0.0
        return {
            "total_debt": float(total_generated),
            "recovered_amount": float(recovered_amount),
            "recovery_rate": rate,
        }

    def _get_total_revenue(self):
        return self._payment_queryset().aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @log_performance(threshold_seconds=1.0)
    def get_sales_details(self):
        """
        Retorna detalles de ventas con optimización de queries.
        OPTIMIZADO: Usa select_related para evitar queries N+1.
        """
        orders = (
            self._order_queryset()
            .select_related("user")  # Ya optimizado
            .prefetch_related("items__variant__product")  # Optimizar acceso a items
            .order_by("-created_at")
        )
        details = []
        for order in orders:
            # Calcular items sin queries adicionales (ya están prefetched)
            item_count = sum(1 for _ in order.items.all())

            details.append(
                {
                    "order_id": str(order.id),
                    "user": order.user.get_full_name() if order.user else "",
                    "user_email": order.user.email if order.user else "",
                    "status": order.status,
                    "total_amount": float(order.total_amount),
                    "item_count": item_count,
                    "delivery_option": order.delivery_option,
                    "created_at": order.created_at.astimezone(self.tz).isoformat(),
                }
            )
        return details

    def get_debt_rows(self):
        """
        Retorna filas de deuda con optimización de queries.
        OPTIMIZADO: Usa select_related y prefetch_related para evitar N+1.
        """
        base_qs = Payment.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        ).select_related("user", "appointment")  # Optimizar relaciones

        debt_related = base_qs.filter(
            Q(status__in=[
                Payment.PaymentStatus.PENDING,
                Payment.PaymentStatus.DECLINED,
                Payment.PaymentStatus.ERROR,
                Payment.PaymentStatus.TIMEOUT,
            ])
            | Q(
                status=Payment.PaymentStatus.APPROVED,
                updated_at__date__gte=self.start_date,
                updated_at__date__lte=self.end_date,
            )
        ).order_by("-created_at")  # Añadir ordenamiento para consistencia

        rows = []
        for payment in debt_related:
            row_data = {
                "payment_id": str(payment.id),
                "user": payment.user.get_full_name() if payment.user else "",
                "user_email": payment.user.email if payment.user else "",
                "user_phone": payment.user.phone_number if payment.user else "",
                "status": payment.status,
                "payment_type": payment.payment_type,
                "amount": float(payment.amount),
                "created_at": payment.created_at.astimezone(self.tz).isoformat(),
                "updated_at": payment.updated_at.astimezone(self.tz).isoformat(),
            }

            # Información de cita si existe (ya está select_related)
            if payment.appointment:
                row_data["appointment_id"] = str(payment.appointment.id)
                row_data["appointment_date"] = payment.appointment.start_time.astimezone(self.tz).isoformat()

            rows.append(row_data)

        return rows
