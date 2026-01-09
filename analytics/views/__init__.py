"""
Paquete Views de Analytics.

Este paquete agrupa todas las vistas del módulo analytics.

Exporta:
- DateFilterMixin: Mixin para parsing de fechas
- audit_analytics: Función de auditoría
- KpiView, TimeSeriesView, AnalyticsExportView: Vistas de KPIs
- CacheClearView: Vista para limpiar caché
- DashboardViewSet: ViewSet del dashboard
- OperationalInsightsView, BusinessIntelligenceView: Vistas de insights
- QueryBuilderSchemaView, QueryBuilderExecuteView, QueryBuilderPresetsView: Vistas del Query Builder
"""
from analytics.views.shared import DateFilterMixin, audit_analytics, build_kpi_service, build_workbook
from analytics.views.cache import CacheClearView
from analytics.views.dashboard import DashboardViewSet
from analytics.views.insights import OperationalInsightsView, BusinessIntelligenceView
from analytics.views.kpi import KpiView, TimeSeriesView, AnalyticsExportView
from analytics.views.query_builder import (
    QueryBuilderSchemaView,
    QueryBuilderExecuteView,
    QueryBuilderPresetsView,
)


__all__ = [
    # Shared
    "DateFilterMixin",
    "audit_analytics",
    "build_kpi_service",
    "build_workbook",
    # Cache
    "CacheClearView",
    # Dashboard
    "DashboardViewSet",
    # Insights
    "OperationalInsightsView",
    "BusinessIntelligenceView",
    # KPI
    "KpiView",
    "TimeSeriesView",
    "AnalyticsExportView",
    # Query Builder
    "QueryBuilderSchemaView",
    "QueryBuilderExecuteView",
    "QueryBuilderPresetsView",
]
