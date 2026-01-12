"""
Views Insights - Endpoints de insights operativos y BI.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analytics.permissions import CanViewFinancialMetrics
from analytics.throttling import AnalyticsRateThrottle
from analytics.views.shared import DateFilterMixin, build_kpi_service


class OperationalInsightsView(DateFilterMixin, viewsets.ViewSet):
    """
    Endpoints para insights operativos (Heatmap, Leaderboard, Funnel).
    Métricas operativas - Solo Admin.
    """
    permission_classes = [CanViewFinancialMetrics]  # Admin only
    throttle_classes = [AnalyticsRateThrottle]

    def list(self, request):
        return Response({"detail": "Use specific actions: heatmap, leaderboard, funnel"})

    def _get_service(self, request):
        start_date, end_date = self._parse_dates(request)
        staff_id, service_category_id = self._parse_filters(request)
        return build_kpi_service(start_date, end_date, staff_id=staff_id, service_category_id=service_category_id)

    @action(detail=False, methods=["get"])
    def heatmap(self, request):
        try:
            service = self._get_service(request)
            data = service.get_heatmap_data()
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        try:
            service = self._get_service(request)
            data = service.get_staff_leaderboard()
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=["get"])
    def funnel(self, request):
        try:
            service = self._get_service(request)
            data = service.get_funnel_metrics()
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=["get"], url_path="top-services")
    def top_services(self, request):
        try:
            service = self._get_service(request)
            data = service.get_top_services()
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=["get"], url_path="status-distribution")
    def status_distribution(self, request):
        try:
            service = self._get_service(request)
            data = service.get_appointment_status_distribution()
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)


class BusinessIntelligenceView(DateFilterMixin, viewsets.ViewSet):
    """
    Endpoints para inteligencia de negocio (Waitlist, Inventory, Retention, Growth).
    Contiene métricas financieras - Solo Admin.
    """
    permission_classes = [CanViewFinancialMetrics]
    throttle_classes = [AnalyticsRateThrottle]

    def list(self, request):
        return Response({"detail": "Use specific actions: waitlist, inventory, retention, growth"})

    def _get_service(self, request):
        start_date, end_date = self._parse_dates(request)
        staff_id, service_category_id = self._parse_filters(request)
        return build_kpi_service(start_date, end_date, staff_id=staff_id, service_category_id=service_category_id)

    @action(detail=False, methods=["get"])
    def waitlist(self, request):
        service = self._get_service(request)
        data = service.get_waitlist_metrics()
        return Response(data)

    @action(detail=False, methods=["get"])
    def inventory(self, request):
        service = self._get_service(request)
        data = service.get_inventory_health()
        return Response(data)

    @action(detail=False, methods=["get"])
    def retention(self, request):
        service = self._get_service(request)
        data = service.get_retention_metrics()
        return Response(data)

    @action(detail=False, methods=["get"])
    def growth(self, request):
        service = self._get_service(request)
        data = service.get_growth_metrics()
        return Response(data)
