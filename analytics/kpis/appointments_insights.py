"""
KPI Appointments Insights - Métricas derivadas de comportamiento.
"""
from collections import defaultdict

from django.db.models import Count, Sum

from spa.models import AppointmentItem


class AppointmentInsightsMixin:
    """Métricas derivadas de comportamiento de citas y staff."""

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
            day_of_week = start_local.isoweekday()  # 1-7
            hour = start_local.hour
            
            heatmap[day_of_week][hour] += 1
            
        # Formatear para frontend: lista de {day, hour, value}
        data = []
        for day in range(1, 8):
            for hour in range(6, 22):  # Asumimos horario operativo 6am-10pm para reducir payload
                data.append({
                    "day": day,
                    "hour": hour,
                    "value": heatmap[day][hour]
                })
        return data

    def get_top_services(self):
        """
        Top servicios por ingresos y cantidad.
        """
        services = (
            AppointmentItem.objects
            .filter(
                appointment__start_time__date__gte=self.start_date,
                appointment__start_time__date__lte=self.end_date
            )
            .values('service__name')
            .annotate(
                count=Count('id'),
                revenue=Sum('price_at_purchase')
            )
            .order_by('-revenue')[:10]
        )

        return [
            {
                "name": item['service__name'],
                "count": item['count'],
                "revenue": float(item['revenue'] or 0)
            }
            for item in services
        ]
