"""
KPI Growth - Métricas de crecimiento, retención y BI.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Case, CharField, Count, Q, Sum, Value, When, F
from django.db.models.functions import Coalesce

from finances.models import Payment
from marketplace.models import InventoryMovement
from spa.models import Appointment


class GrowthMetricsMixin:
    """Métricas de crecimiento, retención y BI."""

    def get_growth_metrics(self):
        """
        Calcula crecimiento WoW (Week over Week) o MoM (Month over Month)
        dependiendo del rango de fechas seleccionado.
        OPTIMIZADO: Usa una sola query con CASE WHEN en lugar de duplicar KpiService.
        """
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
            .filter(user__created_at__date__gte=self.start_date)
            .aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']
        )
        
        # Usuario recurrente = creado antes de este periodo
        returning_user_revenue = (
            self._payment_queryset()
            .filter(user__created_at__date__lt=self.start_date)
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
        from marketplace.models import OrderItem
        
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
