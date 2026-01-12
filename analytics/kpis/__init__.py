"""
Paquete de KPIs de Analytics.

Este paquete agrupa todos los indicadores clave de desempeño (KPIs) del sistema.

Exporta:
- KpiBase: Clase base con querysets y métodos comunes
- AppointmentMetricsMixin: Métricas de citas y utilización
- AppointmentInsightsMixin: Insights de comportamiento (heatmaps, top services)
- FinancialMetricsMixin: Métricas financieras y LTV
- GrowthMetricsMixin: Métricas de crecimiento y retención
- StaffMetricsMixin: Métricas de desempeño de staff
"""
from analytics.kpis.base import KpiBase
from analytics.kpis.appointments import AppointmentMetricsMixin
from analytics.kpis.appointments_insights import AppointmentInsightsMixin
from analytics.kpis.financials import FinancialMetricsMixin
from analytics.kpis.growth import GrowthMetricsMixin
from analytics.kpis.staff import StaffMetricsMixin


__all__ = [
    'KpiBase',
    'AppointmentMetricsMixin',
    'AppointmentInsightsMixin',
    'FinancialMetricsMixin',
    'GrowthMetricsMixin',
    'StaffMetricsMixin',
]
