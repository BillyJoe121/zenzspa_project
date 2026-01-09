"""
KPI Staff - Métricas específicas de desempeño de staff.
"""
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from spa.models import Appointment
from analytics.decorators import log_performance


class StaffMetricsMixin:
    """Métricas específicas de desempeño de staff."""

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
