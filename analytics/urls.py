from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    KpiView, 
    AnalyticsExportView, 
    DashboardViewSet, 
    TimeSeriesView, 
    CacheClearView, 
    OperationalInsightsView, 
    BusinessIntelligenceView,
    QueryBuilderSchemaView,
    QueryBuilderExecuteView,
    QueryBuilderPresetsView,
)

router = DefaultRouter()
router.register(r'dashboard', DashboardViewSet, basename='analytics-dashboard')
router.register(r'ops', OperationalInsightsView, basename='analytics-ops')
router.register(r'bi', BusinessIntelligenceView, basename='analytics-bi')

urlpatterns = [
    path('kpis/', KpiView.as_view(), name='analytics-kpis'),
    path('kpis/export/', AnalyticsExportView.as_view(), name='analytics-export'),
    path('kpis/time-series/', TimeSeriesView.as_view(), name='analytics-time-series'),
    path('cache/clear/', CacheClearView.as_view(), name='analytics-cache-clear'),
    
    # Query Builder endpoints
    path('query-builder/schema/', QueryBuilderSchemaView.as_view(), name='query-builder-schema'),
    path('query-builder/execute/', QueryBuilderExecuteView.as_view(), name='query-builder-execute'),
    path('query-builder/presets/', QueryBuilderPresetsView.as_view(), name='query-builder-presets'),
    
    path('', include(router.urls)),
]
