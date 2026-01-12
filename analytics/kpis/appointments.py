"""
KPI Appointments - Métricas de citas y utilización.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Sum, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from spa.models import Appointment, AppointmentItem, StaffAvailability
from analytics.decorators import log_performance


class AppointmentMetricsMixin:
    """Métricas relacionadas a citas y utilización."""

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

    def get_appointment_status_distribution(self):
        """
        Distribución de estados de citas.
        """
        # Agrupar por status y outcome para mayor detalle
        distribution = (
            self._appointment_queryset()
            .values('status', 'outcome')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        data = []
        for item in distribution:
            label = item['status']
            # Si es cancelada, agregar el motivo (outcome)
            if item['status'] == Appointment.AppointmentStatus.CANCELLED and item['outcome'] != Appointment.AppointmentOutcome.NONE:
                label = f"CANCELLED ({item['outcome']})"
            
            data.append({
                "label": label,
                "value": item['count']
            })
            
        return data
