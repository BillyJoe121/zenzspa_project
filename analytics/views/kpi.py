"""
Views KPI - Endpoints de KPIs, series temporales y exportación.
"""
import csv
import io

from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.permissions import CanViewFinancialMetrics
from analytics.throttling import AnalyticsRateThrottle, AnalyticsExportRateThrottle
from analytics.views.shared import DateFilterMixin, audit_analytics, build_kpi_service, build_workbook


class KpiView(DateFilterMixin, APIView):
    """
    Endpoint que entrega los KPIs de negocio en un rango de fechas.
    Contiene métricas financieras sensibles - Solo Admin.

    Soporta invalidación de caché con ?force_refresh=true
    """

    permission_classes = [CanViewFinancialMetrics]
    throttle_classes = [AnalyticsRateThrottle]

    def get(self, request):
        try:
            start_date, end_date = self._parse_dates(request)
            staff_id, service_category_id = self._parse_filters(request)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        # Soporte para forzar actualización de caché
        force_refresh = request.query_params.get('force_refresh', 'false').lower() == 'true'

        cache_key = self._cache_key(request, "kpis", start_date, end_date, staff_id, service_category_id)
        cached = None if force_refresh else cache.get(cache_key)

        if cached is not None:
            audit_analytics(
                request,
                "kpi_view",
                {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "cache": "hit"},
            )
            return Response(cached)

        service = build_kpi_service(
            start_date,
            end_date,
            staff_id=staff_id,
            service_category_id=service_category_id,
        )
        data = service.get_business_kpis()
        # Option A: Growth Metrics
        data["growth"] = service.get_growth_metrics()
        data["start_date"] = start_date.isoformat()
        data["end_date"] = end_date.isoformat()
        data["staff_id"] = staff_id
        data["service_category_id"] = service_category_id
        data["_cached_at"] = timezone.now().isoformat()

        # Usar TTL dinámico
        ttl = self._get_cache_ttl(start_date, end_date)
        cache.set(cache_key, data, ttl)

        audit_analytics(
            request,
            "kpi_view",
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "cache": "miss" if not force_refresh else "forced_refresh"
            },
        )
        return Response(data)


class TimeSeriesView(DateFilterMixin, APIView):
    """
    Endpoint para datos de gráficos (ingresos y citas por día).
    Contiene datos financieros - Solo Admin.
    """
    permission_classes = [CanViewFinancialMetrics]
    throttle_classes = [AnalyticsRateThrottle]

    def get(self, request):
        try:
            start_date, end_date = self._parse_dates(request)
            staff_id, service_category_id = self._parse_filters(request)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        cache_key = self._cache_key(request, "timeseries", start_date, end_date, staff_id, service_category_id)
        cached = cache.get(cache_key)
        if cached is not None:
            audit_analytics(request, "timeseries_view", {"cache": "hit"})
            return Response(cached)

        service = build_kpi_service(
            start_date,
            end_date,
            staff_id=staff_id,
            service_category_id=service_category_id,
        )
        data = service.get_time_series()

        ttl = self._get_cache_ttl(start_date, end_date)
        cache.set(cache_key, data, ttl)
        audit_analytics(request, "timeseries_view", {"cache": "miss"})

        return Response(data)


class AnalyticsExportView(DateFilterMixin, APIView):
    """Exportación de analytics - Solo Admin."""
    permission_classes = [CanViewFinancialMetrics]
    throttle_classes = [AnalyticsExportRateThrottle]

    def get(self, request):
        try:
            start_date, end_date = self._parse_dates(request)
            staff_id, service_category_id = self._parse_filters(request)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        service = build_kpi_service(
            start_date,
            end_date,
            staff_id=staff_id,
            service_category_id=service_category_id,
        )
        cache_key = self._cache_key(request, "dataset", start_date, end_date, staff_id, service_category_id)
        dataset = cache.get(cache_key)
        cache_state = "hit"
        if dataset is None:
            cache_state = "miss"
            kpis = service.get_business_kpis()
            dataset = {
                "kpis": kpis,
                "rows": service.as_rows(),
                "sales_details": service.get_sales_details(),
                "debt_metrics": kpis.get("debt_recovery", {}),
                "debt_rows": service.get_debt_rows(),
            }
            # CAMBIAR - Usar TTL dinámico
            ttl = self._get_cache_ttl(start_date, end_date)
            cache.set(cache_key, dataset, ttl)
        kpis = dataset["kpis"]
        export_format = request.query_params.get("format", "csv").lower()
        if export_format == "xlsx":
            workbook = build_workbook(
                kpis=kpis,
                sales_details=dataset["sales_details"],
                debt_metrics=dataset["debt_metrics"],
                debt_rows=dataset["debt_rows"],
                start_date=start_date,
                end_date=end_date,
            )
            filename = f"analytics_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
            response = HttpResponse(
                workbook,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            audit_analytics(
                request,
                "analytics_export",
                {
                    "format": "xlsx",
                    "cache": cache_state,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            return response

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value", "start_date", "end_date"])
        for metric, value in dataset["rows"]:
            writer.writerow([metric, value, start_date.isoformat(), end_date.isoformat()])

        filename = f"analytics_{start_date.isoformat()}_{end_date.isoformat()}.csv"
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        audit_analytics(
            request,
            "analytics_export",
            {
                "format": "csv",
                "cache": cache_state,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        return response
