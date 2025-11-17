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
from django.db.models.functions import Coalesce
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
            qs = qs.filter(items__service__category_id=self.service_category_id)
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
            status__in=[
                Appointment.AppointmentStatus.COMPLETED,
                Appointment.AppointmentStatus.NO_SHOW,
            ]
        )
        total_finished = finished.count()
        if total_finished == 0:
            return 0
        no_show = finished.filter(status=Appointment.AppointmentStatus.NO_SHOW).count()
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

    def _payment_queryset(self):
        return Payment.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ],
        )

    def _order_queryset(self):
        return Order.objects.filter(
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        )

    def _get_ltv_by_role(self):
        """
        LTV por Rol = suma(total gastado por rol) ÷ cantidad de usuarios por rol.
        """
        user_totals = defaultdict(Decimal)
        payments = self._payment_queryset().values("user_id").annotate(amount=Sum("amount"))
        for row in payments:
            if row["user_id"]:
                user_totals[row["user_id"]] += row["amount"] or Decimal("0")
        orders = self._order_queryset().values("user_id").annotate(amount=Sum("total_amount"))
        for row in orders:
            if row["user_id"]:
                user_totals[row["user_id"]] += row["amount"] or Decimal("0")

        if not user_totals:
            return {}

        users = CustomUser.objects.filter(id__in=user_totals.keys()).values("id", "role")
        role_totals = defaultdict(Decimal)
        role_counts = defaultdict(int)
        for user in users:
            role = user["role"] or CustomUser.Role.CLIENT
            total_spent = user_totals.get(user["id"], Decimal("0"))
            if total_spent > 0:
                role_totals[role] += total_spent
                role_counts[role] += 1

        results = {}
        for role, amount in role_totals.items():
            count = role_counts.get(role) or 1
            results[role] = {
                "ltv": float(amount / count),
                "total_spent": float(amount),
                "user_count": count,
            }
        return results

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
        scheduled = appointment_minutes.aggregate(total=Sum("duration"))["total"] or 0
        available = self._calculate_available_minutes()
        if available == 0:
            return 0
        return scheduled / available

    def _calculate_available_minutes(self):
        """
        Minutos disponibles = suma de (fin - inicio) para cada disponibilidad entre start_date y end_date.
        """
        availabilities = StaffAvailability.objects.all()
        if self.staff_id:
            availabilities = availabilities.filter(staff_member_id=self.staff_id)
        total_minutes = 0
        mapping = defaultdict(list)
        for availability in availabilities:
            mapping[availability.day_of_week].append(availability)

        current = self.start_date
        while current <= self.end_date:
            for availability in mapping.get(current.isoweekday(), []):
                delta = (
                    datetime.combine(current, availability.end_time)
                    - datetime.combine(current, availability.start_time)
                ).total_seconds() / 60
                if delta > 0:
                    total_minutes += delta
            current += timedelta(days=1)
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
        rate = float(recovered_amount / total_generated) if total_generated > 0 else 0.0
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
        rows.append(("debt_recovery_rate", debt_metrics.get("recovery_rate", 0)))
        return rows
