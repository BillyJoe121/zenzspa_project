"""
Servicios de Analytics (KPI y BI).

Se refactorizó en mixins específicos para mantener responsabilidades claras
sin cambiar la interfaz pública: `KpiService` sigue importable desde aquí.
"""

from analytics.kpis import (
    KpiBase,
    AppointmentMetricsMixin,
    AppointmentInsightsMixin,
    FinancialMetricsMixin,
    GrowthMetricsMixin,
    StaffMetricsMixin,
)


class KpiService(
    AppointmentMetricsMixin,
    AppointmentInsightsMixin,
    FinancialMetricsMixin,
    GrowthMetricsMixin,
    StaffMetricsMixin,
    KpiBase,
):
    """Servicio principal para KPIs."""


__all__ = ["KpiService"]
