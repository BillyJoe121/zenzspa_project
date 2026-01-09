"""
KPI Base - Clase base para todos los KPIs.
"""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from finances.models import Payment
from marketplace.models import Order
from spa.models import Appointment
from analytics.decorators import log_performance


class KpiBase:
    """
    Calcula los indicadores operativos clave combinando los modelos
    de spa y marketplace.
    """

    def __init__(self, start_date, end_date, *, staff_id=None, service_category_id=None):
        if start_date is None or end_date is None:
            raise ValueError("Debes especificar fechas de inicio y fin.")
        if start_date > end_date:
            raise ValueError("La fecha de inicio no puede ser mayor a la fecha de fin.")
        if (end_date - start_date).days > 365:
            raise ValueError("El rango de fechas no puede exceder 365 días.")
        self.start_date = start_date
        self.end_date = end_date
        self.staff_id = staff_id
        self.service_category_id = service_category_id
        self.tz = ZoneInfo(settings.TIME_ZONE)  # Usar timezone de settings

    @log_performance(threshold_seconds=0.5)
    def get_business_kpis(self):
        return {
            "conversion_rate": self._get_conversion_rate(),
            "no_show_rate": self._get_no_show_rate(),
            "reschedule_rate": self._get_reschedule_rate(),
            "ltv_by_role": self._get_ltv_by_role(),
            "utilization_rate": self._get_utilization_rate(),
            "average_order_value": self._get_average_order_value(),
            "debt_recovery": self._get_debt_recovery_metrics(),
            "total_revenue": self._get_total_revenue(),
        }

    def _appointment_queryset(self):
        qs = Appointment.objects.filter(
            start_time__date__gte=self.start_date,
            start_time__date__lte=self.end_date,
        )
        if self.staff_id:
            qs = qs.filter(staff_member_id=self.staff_id)
        if self.service_category_id:
            qs = qs.filter(
                items__service__category_id=self.service_category_id)
        return qs.distinct()

    def _excluded_payment_types(self):
        excluded = [Payment.PaymentType.TIP]
        adjustment_type = getattr(Payment.PaymentType, "ADJUSTMENT", None)
        if adjustment_type:
            excluded.append(adjustment_type)
        return excluded

    def _payment_queryset(self):
        qs = Payment.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ],
        )
        excluded_types = self._excluded_payment_types()
        if excluded_types:
            qs = qs.exclude(payment_type__in=excluded_types)
        return qs

    def _order_queryset(self):
        return Order.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        )

    def as_rows(self):
        kpis = self.get_business_kpis()
        rows = [
            ("conversion_rate", kpis["conversion_rate"]),
            ("no_show_rate", kpis["no_show_rate"]),
            ("reschedule_rate", kpis["reschedule_rate"]),
            ("utilization_rate", kpis["utilization_rate"]),
            ("average_order_value", kpis["average_order_value"]),
        ]
        for role, payload in kpis["ltv_by_role"].items():
            rows.append((f"ltv_{role.lower()}", payload["ltv"]))
        debt_metrics = kpis.get("debt_recovery") or {}
        rows.append(("debt_total", debt_metrics.get("total_debt", 0)))
        rows.append(("debt_recovered", debt_metrics.get("recovered_amount", 0)))
        rows.append(
            ("debt_recovery_rate", debt_metrics.get("recovery_rate", 0)))
        return rows
