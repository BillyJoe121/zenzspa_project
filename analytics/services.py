from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import (
    Sum,
    Avg,
    Count,
    Q,
    F,
    ExpressionWrapper,
    DurationField,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from spa.models import Appointment, AppointmentItem, StaffAvailability, Payment, ClientCredit
from marketplace.models import Order
from users.models import CustomUser


class KpiService:
    """
    Calcula los indicadores operativos clave combinando los modelos
    de spa y marketplace.
    """

    def __init__(self, start_date, end_date, *, staff_id=None, service_category_id=None):
        self.start_date = start_date
        self.end_date = end_date
        self.staff_id = staff_id
        self.service_category_id = service_category_id
        self.tz = ZoneInfo("America/Bogota")

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

    # --- Appointment helpers -------------------------------------------------

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

    def _get_conversion_rate(self):
        """
        Conversion Rate = citas confirmadas o completadas ÷ total de citas creadas en el periodo.
        """
        appointments = self._appointment_queryset()
        total = appointments.count()
        if total == 0:
            return 0
        converted = appointments.filter(
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.RESCHEDULED,
                Appointment.AppointmentStatus.COMPLETED,
            ]
        ).count()
        return converted / total

    def _get_no_show_rate(self):
        """
        No-Show Rate = citas marcadas como NO_SHOW ÷ citas finalizadas (COMPLETED + NO_SHOW).
        """
        appointments = self._appointment_queryset()
        finished = appointments.filter(
            Q(status=Appointment.AppointmentStatus.COMPLETED)
            | Q(
                status=Appointment.AppointmentStatus.CANCELLED,
                outcome=Appointment.AppointmentOutcome.NO_SHOW,
            )
        )
        total_finished = finished.count()
        if total_finished == 0:
            return 0
        no_show = finished.filter(
            outcome=Appointment.AppointmentOutcome.NO_SHOW).count()
        return no_show / total_finished

    def _get_reschedule_rate(self):
        """
        Reschedule Rate = citas con reschedule_count>0 ÷ total de citas del periodo.
        """
        appointments = self._appointment_queryset()
        total = appointments.count()
        if total == 0:
            return 0
        rescheduled = appointments.filter(reschedule_count__gt=0).count()
        return rescheduled / total

    # --- Financial metrics ---------------------------------------------------

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

    def _get_utilization_rate(self):
        """
        Utilización = minutos reservados ÷ minutos disponibles de las agendas del personal.
        """
        appointment_minutes = AppointmentItem.objects.filter(
            appointment__start_time__date__gte=self.start_date,
            appointment__start_time__date__lte=self.end_date,
        )
        if self.staff_id:
            appointment_minutes = appointment_minutes.filter(
                appointment__staff_member_id=self.staff_id
            )
        if self.service_category_id:
            appointment_minutes = appointment_minutes.filter(
                service__category_id=self.service_category_id
            )
        scheduled = appointment_minutes.aggregate(
            total=Sum("duration"))["total"] or 0
        available = self._calculate_available_minutes()
        if available == 0:
            return 0
        return scheduled / available

    def _calculate_available_minutes(self):
        """
        Minutos disponibles = suma de (fin - inicio) para cada disponibilidad.
        CORREGIDO: Cálculo en Python para evitar problemas con TimeField en DB.
        """
        availabilities = StaffAvailability.objects.all()
        if self.staff_id:
            availabilities = availabilities.filter(staff_member_id=self.staff_id)

        # Contar ocurrencias de cada día de semana en el rango
        day_counts = defaultdict(int)
        current = self.start_date
        while current <= self.end_date:
            day_counts[current.isoweekday()] += 1
            current += timedelta(days=1)

        total_minutes = 0
        # Iterar en Python para calcular duración segura
        for availability in availabilities:
            occurrences = day_counts.get(availability.day_of_week, 0)
            if occurrences == 0:
                continue
            
            # Calcular duración en minutos
            start = availability.start_time
            end = availability.end_time
            # Convertir a minutos desde medianoche
            start_minutes = start.hour * 60 + start.minute
            end_minutes = end.hour * 60 + end.minute
            
            duration = max(0, end_minutes - start_minutes)
            total_minutes += duration * occurrences

        return total_minutes

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

    def get_sales_details(self):
        orders = (
            self._order_queryset()
            .select_related("user")
            .order_by("-created_at")
        )
        details = []
        for order in orders:
            details.append(
                {
                    "order_id": str(order.id),
                    "user": order.user.get_full_name() if order.user else "",
                    "status": order.status,
                    "total_amount": float(order.total_amount),
                    "created_at": order.created_at.astimezone(self.tz).isoformat(),
                }
            )
        return details

    def get_debt_rows(self):
        base_qs = Payment.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        ).select_related("user")
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
        )
        rows = []
        for payment in debt_related:
            rows.append(
                {
                    "payment_id": str(payment.id),
                    "user": payment.user.get_full_name() if payment.user else "",
                    "status": payment.status,
                    "amount": float(payment.amount),
                    "created_at": payment.created_at.astimezone(self.tz).isoformat(),
                    "updated_at": payment.updated_at.astimezone(self.tz).isoformat(),
                }
            )
        return rows

    def _get_total_revenue(self):
        return self._payment_queryset().aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_time_series(self, interval="day"):
        """
        Retorna datos de series de tiempo para gráficos.
        Agrupa ingresos y conteo de citas por fecha.
        """
        # 1. Ingresos por fecha
        revenue_qs = (
            self._payment_queryset()
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(total=Sum("amount"))
            .order_by("date")
        )
        revenue_map = {entry["date"]: float(entry["total"]) for entry in revenue_qs}

        # 2. Citas por fecha
        appointments_qs = (
            self._appointment_queryset()
            .annotate(date=TruncDate("start_time"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        appointments_map = {entry["date"]: entry["count"] for entry in appointments_qs}

        # 3. Combinar y rellenar fechas faltantes
        series = []
        current = self.start_date
        while current <= self.end_date:
            series.append({
                "date": current.isoformat(),
                "revenue": revenue_map.get(current, 0.0),
                "appointments": appointments_map.get(current, 0),
            })
            current += timedelta(days=1)
        
        return series

    # --- Export helpers ------------------------------------------------------

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
