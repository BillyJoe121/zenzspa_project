from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import KpiView, AnalyticsExportView, DashboardViewSet

router = DefaultRouter()
router.register(r'dashboard', DashboardViewSet, basename='analytics-dashboard')

urlpatterns = [
    path('kpis/', KpiView.as_view(), name='analytics-kpis'),
    path('kpis/export/', AnalyticsExportView.as_view(), name='analytics-export'),
    path('', include(router.urls)),
]
