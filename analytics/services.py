from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
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
from .decorators import log_performance


class KpiService:
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
                Appointment.AppointmentStatus.FULLY_PAID,
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

    def _get_total_revenue(self):
        return self._payment_queryset().aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @log_performance(threshold_seconds=0.5)
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

    # --- 360 Business Intelligence (Option C) --------------------------------

    def get_growth_metrics(self):
        """
        Calcula crecimiento WoW (Week over Week) o MoM (Month over Month)
        dependiendo del rango de fechas seleccionado.
        OPTIMIZADO: Usa una sola query con CASE WHEN en lugar de duplicar KpiService.
        """
        from django.db.models import Case, When, Value, CharField
        
        # Determinar periodo anterior
        duration = self.end_date - self.start_date
        previous_start = self.start_date - duration - timedelta(days=1)
        previous_end = self.end_date - duration - timedelta(days=1)

        # Query única para ambos periodos - REVENUE
        revenue_data = (
            Payment.objects
            .filter(
                Q(created_at__date__gte=previous_start, created_at__date__lte=previous_end) |
                Q(created_at__date__gte=self.start_date, created_at__date__lte=self.end_date),
                status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT]
            )
            .annotate(
                period=Case(
                    When(created_at__date__gte=self.start_date, then=Value('current')),
                    default=Value('previous'),
                    output_field=CharField()
                )
            )
            .values('period')
            .annotate(total=Coalesce(Sum('amount'), Decimal('0')))
        )
        
        revenue_dict = {item['period']: item['total'] for item in revenue_data}
        current_revenue = revenue_dict.get('current', Decimal('0'))
        previous_revenue = revenue_dict.get('previous', Decimal('0'))

        # Query única para ambos periodos - APPOINTMENTS
        appt_data = (
            Appointment.objects
            .filter(
                Q(start_time__date__gte=previous_start, start_time__date__lte=previous_end) |
                Q(start_time__date__gte=self.start_date, start_time__date__lte=self.end_date)
            )
            .annotate(
                period=Case(
                    When(start_time__date__gte=self.start_date, then=Value('current')),
                    default=Value('previous'),
                    output_field=CharField()
                )
            )
            .values('period')
            .annotate(count=Count('id'))
        )
        
        appt_dict = {item['period']: item['count'] for item in appt_data}
        current_appointments = appt_dict.get('current', 0)
        previous_appointments = appt_dict.get('previous', 0)

        def calculate_growth(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return float(((current - previous) / previous) * 100)

        return {
            "revenue": {
                "current": float(current_revenue),
                "previous": float(previous_revenue),
                "growth_rate": calculate_growth(current_revenue, previous_revenue)
            },
            "appointments": {
                "current": current_appointments,
                "previous": previous_appointments,
                "growth_rate": calculate_growth(current_appointments, previous_appointments)
            }
        }

    def get_retention_metrics(self):
        """
        Análisis de Cohortes simplificado:
        - Ingresos de clientes nuevos vs recurrentes en el periodo.
        OPTIMIZADO: Usa agregación en DB en lugar de iterar en memoria.
        """
        # Usuario nuevo = creado en este periodo
        new_user_revenue = (
            self._payment_queryset()
            .filter(user__date_joined__date__gte=self.start_date)
            .aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']
        )
        
        # Usuario recurrente = creado antes de este periodo
        returning_user_revenue = (
            self._payment_queryset()
            .filter(user__date_joined__date__lt=self.start_date)
            .aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']
        )
        
        total = new_user_revenue + returning_user_revenue
        
        return {
            "revenue_breakdown": {
                "new_users": float(new_user_revenue),
                "returning_users": float(returning_user_revenue),
                "total": float(total),
                "new_users_pct": float(new_user_revenue / total * 100) if total > 0 else 0
            }
        }

    def get_heatmap_data(self):
        """
        Retorna datos para mapa de calor: Ocupación por Día de Semana vs Hora.
        """
        appointments = self._appointment_queryset()
        
        # Inicializar matriz 7 dias x 24 horas (o rango operativo)
        # 1=Lunes, 7=Domingo
        heatmap = defaultdict(lambda: defaultdict(int))
        
        for appt in appointments:
            # Convertir a zona horaria local
            start_local = appt.start_time.astimezone(self.tz)
            day_of_week = start_local.isoweekday() # 1-7
            hour = start_local.hour
            
            heatmap[day_of_week][hour] += 1
            
        # Formatear para frontend: lista de {day, hour, value}
        data = []
        for day in range(1, 8):
            for hour in range(6, 22): # Asumimos horario operativo 6am-10pm para reducir payload
                data.append({
                    "day": day,
                    "hour": hour,
                    "value": heatmap[day][hour]
                })
        return data

    @log_performance(threshold_seconds=0.3)
    def get_staff_leaderboard(self):
        """
        Ranking de staff por ingresos y citas.
        OPTIMIZADO: Usa una sola query con agregación en lugar de N+1.
        """
        # Construir query base con filtros
        base_query = Appointment.objects.filter(
            start_time__date__gte=self.start_date,
            start_time__date__lte=self.end_date,
            status=Appointment.AppointmentStatus.COMPLETED
        )
        
        # Aplicar filtro de staff si existe
        if self.staff_id:
            base_query = base_query.filter(staff_member_id=self.staff_id)
        
        # Agregar por staff member con una sola query
        leaderboard_data = (
            base_query
            .values('staff_member__id', 'staff_member__first_name', 'staff_member__last_name')
            .annotate(
                revenue=Coalesce(Sum('price_at_purchase'), Decimal('0')),
                appointments=Count('id')
            )
            .order_by('-revenue')
        )
        
        # Formatear resultados
        leaderboard = [
            {
                "staff_id": str(item['staff_member__id']),
                "name": f"{item['staff_member__first_name']} {item['staff_member__last_name']}".strip(),
                "revenue": float(item['revenue']),
                "appointments": item['appointments']
            }
            for item in leaderboard_data
            if item['staff_member__id']  # Filtrar nulls
        ]
        
        return leaderboard

    def get_waitlist_metrics(self):
        """
        Métricas de demanda insatisfecha.
        """
        from spa.models import WaitlistEntry
        
        entries = WaitlistEntry.objects.filter(
            desired_date__gte=self.start_date,
            desired_date__lte=self.end_date
        )
        
        total_entries = entries.count()
        by_status = entries.values('status').annotate(count=Count('id'))
        
        # Estimar valor perdido (Demanda no atendida)
        # Asumimos promedio de precio de servicios solicitados
        waiting_entries = entries.filter(status=WaitlistEntry.Status.WAITING)
        lost_revenue_estimate = 0
        for entry in waiting_entries:
            # Promedio de precio de servicios en la entry
            avg_price = entry.services.aggregate(avg=Avg('price'))['avg'] or 0
            lost_revenue_estimate += float(avg_price)

        return {
            "total_entries": total_entries,
            "by_status": {item['status']: item['count'] for item in by_status},
            "estimated_lost_revenue": lost_revenue_estimate
        }

    def get_inventory_health(self):
        """
        Métricas de inventario: Top productos y mermas.
        """
        from marketplace.models import ProductVariant, InventoryMovement, OrderItem
        
        # 1. Top Productos Vendidos (Pareto)
        top_products = (
            OrderItem.objects
            .filter(order__created_at__date__gte=self.start_date, order__created_at__date__lte=self.end_date)
            .values('variant__product__name', 'variant__name')
            .annotate(total_sold=Sum('quantity'), total_revenue=Sum(F('quantity') * F('price_at_purchase')))
            .order_by('-total_revenue')[:10]
        )
        
        # 2. Mermas (Ajustes negativos)
        shrinkage = (
            InventoryMovement.objects
            .filter(
                created_at__date__gte=self.start_date, 
                created_at__date__lte=self.end_date,
                movement_type=InventoryMovement.MovementType.ADJUSTMENT,
                quantity__lt=0
            )
            .aggregate(
                total_items=Sum('quantity'), # Será negativo
                # Para valor monetario necesitaríamos costo, usaremos precio como proxy o nada por ahora
            )
        )
        
        return {
            "top_products": [
                {
                    "name": f"{item['variant__product__name']} - {item['variant__name']}",
                    "sold": item['total_sold'],
                    "revenue": float(item['total_revenue'])
                }
                for item in top_products
            ],
            "shrinkage_items": abs(shrinkage['total_items'] or 0)
        }

    def get_funnel_metrics(self):
        """
        Embudo de conversión de citas.
        """
        qs = self._appointment_queryset()
        total = qs.count()
        confirmed = qs.filter(status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.FULLY_PAID, Appointment.AppointmentStatus.COMPLETED]).count()
        completed = qs.filter(status=Appointment.AppointmentStatus.COMPLETED).count()
        
        return {
            "steps": [
                {"name": "Solicitadas", "value": total},
                {"name": "Confirmadas", "value": confirmed},
                {"name": "Completadas", "value": completed}
            ],
            "conversion_rate": float(completed / total * 100) if total > 0 else 0
        }
