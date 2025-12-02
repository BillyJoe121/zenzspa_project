from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from analytics.permissions import (
    CanViewAnalytics,
    CanViewFinancialMetrics,
    CanViewOperationalMetrics,
)
from analytics.views import AnalyticsExportView, CacheClearView, KpiView, TimeSeriesView
from users.models import CustomUser


class AnalyticsPermissionsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = CustomUser.objects.create_user(
            phone_number="+573001111111",
            email="admin-perms@example.com",
            first_name="Admin",
            password="pass123",
            role=CustomUser.Role.ADMIN,
        )
        self.staff = CustomUser.objects.create_user(
            phone_number="+573001111112",
            email="staff-perms@example.com",
            first_name="Staff",
            password="pass123",
            role=CustomUser.Role.STAFF,
        )
        self.staff_flag = CustomUser.objects.create_user(
            phone_number="+573001111113",
            email="djangostaff@example.com",
            first_name="FlagStaff",
            password="pass123",
            role=CustomUser.Role.CLIENT,
            is_staff=True,
        )
        self.client_user = CustomUser.objects.create_user(
            phone_number="+573001111114",
            email="client-perms@example.com",
            first_name="Client",
            password="pass123",
            role=CustomUser.Role.CLIENT,
        )

    def _make_request(self, user):
        request = self.factory.get("/dummy/")
        request.user = user
        return request

    def test_can_view_analytics_denies_anonymous_and_client(self):
        anon_request = self._make_request(None)
        self.assertFalse(CanViewAnalytics().has_permission(anon_request, None))

        client_request = self._make_request(self.client_user)
        self.assertFalse(CanViewAnalytics().has_permission(client_request, None))

    def test_can_view_analytics_allows_admin_and_staff_variants(self):
        admin_request = self._make_request(self.admin)
        self.assertTrue(CanViewAnalytics().has_permission(admin_request, None))

        staff_request = self._make_request(self.staff)
        self.assertTrue(CanViewAnalytics().has_permission(staff_request, None))

        flag_request = self._make_request(self.staff_flag)
        self.assertTrue(CanViewAnalytics().has_permission(flag_request, None))

    def test_financial_metrics_only_admin(self):
        perm = CanViewFinancialMetrics()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))
        self.assertFalse(perm.has_permission(self._make_request(self.staff), None))
        self.assertFalse(perm.has_permission(self._make_request(self.client_user), None))

    def test_operational_metrics_allow_staff_and_admin(self):
        perm = CanViewOperationalMetrics()
        self.assertTrue(perm.has_permission(self._make_request(self.admin), None))
        self.assertTrue(perm.has_permission(self._make_request(self.staff), None))
        self.assertFalse(perm.has_permission(self._make_request(self.client_user), None))


class AnalyticsViewsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = CustomUser.objects.create_user(
            phone_number="+573002222221",
            email="views-admin@example.com",
            first_name="AdminView",
            password="pass123",
            role=CustomUser.Role.ADMIN,
        )
        # Evitar errores de versionado en tests unitarios
        self.prev_versioning_class = AnalyticsExportView.versioning_class
        AnalyticsExportView.versioning_class = None
        self.kpi_view = KpiView.as_view()
        self.timeseries_view = TimeSeriesView.as_view()
        self.export_view = AnalyticsExportView.as_view()
        self.cache_clear_view = CacheClearView.as_view()
        cache.clear()

    def tearDown(self):
        AnalyticsExportView.versioning_class = self.prev_versioning_class

    def _force_version(self, request):
        request.version = "v1"
        request.resolver_match = SimpleNamespace(namespace="v1")
        return request

    def _auth_get(self, path, query=None):
        request = self.factory.get(path, query or {})
        force_authenticate(request, user=self.admin)
        return self._force_version(request)

    def test_kpi_view_returns_400_for_future_dates(self):
        future = timezone.localdate() + timedelta(days=1)
        request = self._auth_get(
            "/kpis/",
            {"start_date": future.isoformat(), "end_date": future.isoformat()},
        )
        response = self.kpi_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_time_series_returns_400_for_invalid_staff_filter(self):
        request = self._auth_get("/kpis/time-series/", {"staff_id": "invalid"})
        response = self.timeseries_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    @patch("analytics.views._audit_analytics")
    @patch("analytics.views.KpiService")
    def test_time_series_cache_hit_skips_service(self, mock_service_cls, mock_audit):
        mock_service = mock_service_cls.return_value
        mock_service.get_time_series.return_value = {"series": [1]}

        first_request = self._auth_get("/kpis/time-series/")
        first_response = self.timeseries_view(first_request)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.data, {"series": [1]})

        second_request = self._auth_get("/kpis/time-series/")
        second_response = self.timeseries_view(second_request)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.data, {"series": [1]})

        self.assertEqual(mock_service.get_time_series.call_count, 1)
        self.assertTrue(mock_audit.called)

    @patch("analytics.views.build_analytics_workbook", return_value=b"binary-data")
    @patch("analytics.views._audit_analytics")
    @patch("analytics.views.KpiService")
    def test_export_view_returns_xlsx(self, mock_service_cls, mock_audit, mock_build):
        mock_service = mock_service_cls.return_value
        mock_service.get_business_kpis.return_value = {
            "metric": 1,
            "debt_recovery": {"total_debt": 0},
        }
        mock_service.as_rows.return_value = [("metric", 1)]
        mock_service.get_sales_details.return_value = []
        mock_service.get_debt_rows.return_value = []

        request = self._auth_get("/api/v1/analytics/kpis/export/", {"format": "xlsx"})
        response = self.export_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(response.content, b"binary-data")
        mock_build.assert_called_once()
        self.assertTrue(mock_audit.called)

    @patch("analytics.views._audit_analytics")
    @patch("analytics.views.KpiService")
    def test_export_view_reuses_cached_dataset(self, mock_service_cls, mock_audit):
        mock_service = mock_service_cls.return_value
        mock_service.get_business_kpis.return_value = {"debt_recovery": {}}
        mock_service.as_rows.return_value = [("metric", 1)]
        mock_service.get_sales_details.return_value = []
        mock_service.get_debt_rows.return_value = []

        first_request = self._auth_get("/api/v1/analytics/kpis/export/", {"format": "csv"})
        first_response = self.export_view(first_request)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response["Content-Type"], "text/csv")

        second_request = self._auth_get("/api/v1/analytics/kpis/export/", {"format": "csv"})
        second_response = self.export_view(second_request)
        self.assertEqual(second_response.status_code, 200)

        self.assertEqual(mock_service.get_business_kpis.call_count, 1)
        self.assertEqual(mock_service.as_rows.call_count, 1)
        self.assertEqual(mock_service.get_sales_details.call_count, 1)
        self.assertEqual(mock_service.get_debt_rows.call_count, 1)
        self.assertTrue(mock_audit.called)

    @patch("analytics.views._audit_analytics")
    def test_cache_clear_rejects_invalid_scope(self, mock_audit):
        request = self.factory.post("/cache/clear/", {"scope": "invalid"}, format="json")
        force_authenticate(request, user=self.admin)
        request = self._force_version(request)
        response = self.cache_clear_view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        mock_audit.assert_not_called()

    @patch("analytics.views._audit_analytics")
    def test_cache_clear_all_fallback(self, mock_audit):
        cache.set("analytics:test:key", "value")
        request = self.factory.post("/cache/clear/", {"scope": "all"}, format="json")
        force_authenticate(request, user=self.admin)
        request = self._force_version(request)
        response = self.cache_clear_view(request)

        self.assertEqual(response.status_code, 200)
        cleared = response.data["cleared_count"]
        if isinstance(cleared, int):
            self.assertGreaterEqual(cleared, 1)
        else:
            self.assertEqual(cleared, "all")
        self.assertTrue(mock_audit.called)
