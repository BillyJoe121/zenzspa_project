from datetime import datetime, timedelta
import csv
import io

from decimal import Decimal

from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

from spa.models import Appointment, Payment, ClientCredit
from marketplace.models import Order
from users.models import CustomUser
from users.permissions import IsStaffOrAdmin
from core.models import AuditLog
from core.utils import safe_audit_log
from .services import KpiService
from .utils import build_analytics_workbook
from .permissions import CanViewAnalytics, CanViewFinancialMetrics, CanViewOperationalMetrics
from .throttling import AnalyticsRateThrottle, AnalyticsExportRateThrottle


def _audit_analytics(request, action, extra=None):
    safe_audit_log(
        action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
        admin_user=getattr(request, "user", None),
        details={
            "analytics_action": action,
            **(extra or {}),
        },
    )


class DateFilterMixin:
    MAX_RANGE_DAYS = 31
    CACHE_TTL_SHORT = 300      # 5 minutos - para datos en tiempo real
    CACHE_TTL_MEDIUM = 1800    # 30 minutos - para KPIs diarios
    CACHE_TTL_LONG = 7200      # 2 horas - para reportes históricos

    def _get_cache_ttl(self, start_date, end_date):
        """
        Determina TTL basado en qué tan antiguo es el rango.
        """
        today = timezone.localdate()
        
        # Si el rango incluye hoy, usar TTL corto
        if end_date >= today:
            return self.CACHE_TTL_SHORT
        
        # Si el rango es de la semana pasada, usar TTL medio
        week_ago = today - timedelta(days=7)
        if start_date >= week_ago:
            return self.CACHE_TTL_MEDIUM
        
        # Para datos históricos, usar TTL largo
        return self.CACHE_TTL_LONG

    def _parse_dates(self, request):
        today = timezone.localdate()
        default_start = today - timedelta(days=6)

        def parse_param(name, default):
            value = request.query_params.get(name)
            if not value:
                return default
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"Formato inválido para {name}. Usa YYYY-MM-DD.")
            
            # NUEVO - Validar que no sea fecha futura
            if parsed > today:
                raise ValueError(f"{name} no puede ser una fecha futura.")
            
            # NUEVO - Validar que no sea muy antigua (máximo 1 año)
            one_year_ago = today - timedelta(days=365)
            if parsed < one_year_ago:
                raise ValueError(f"{name} no puede ser anterior a {one_year_ago.isoformat()}.")
            
            return parsed

        start_date = parse_param("start_date", default_start)
        end_date = parse_param("end_date", today)
        
        if start_date > end_date:
            raise ValueError("start_date debe ser menor o igual a end_date.")
        
        # NUEVO - Validar rango máximo basado en rol
        user = getattr(request, 'user', None)
        max_days = self.MAX_RANGE_DAYS
        
        # Admins pueden consultar hasta 90 días
        if user and getattr(user, 'role', None) == CustomUser.Role.ADMIN:
            max_days = 90
        
        if (end_date - start_date).days > max_days:
            raise ValueError(
                f"El rango máximo permitido es de {max_days} días para tu rol."
            )
        
        return start_date, end_date

    def _parse_filters(self, request):
        staff_id = request.query_params.get("staff_id")
        service_category_id = request.query_params.get("service_category_id")
        try:
            staff_id = int(staff_id) if staff_id else None
        except ValueError:
            raise ValueError("staff_id debe ser numérico.")
        try:
            service_category_id = int(service_category_id) if service_category_id else None
        except ValueError:
            raise ValueError("service_category_id debe ser numérico.")
        return staff_id, service_category_id

    def _cache_key(self, request, prefix, start_date, end_date, staff_id, service_category_id):
        role = getattr(getattr(request, "user", None), "role", "ANON")
        return ":".join(
            [
                "analytics",
                prefix,
                str(role),
                start_date.isoformat(),
                end_date.isoformat(),
                str(staff_id or "all"),
                str(service_category_id or "all"),
            ]
        )


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
            _audit_analytics(
                request,
                "kpi_view",
                {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "cache": "hit"},
            )
            return Response(cached)

        service = KpiService(
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

        _audit_analytics(
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
            _audit_analytics(request, "timeseries_view", {"cache": "hit"})
            return Response(cached)

        service = KpiService(
            start_date,
            end_date,
            staff_id=staff_id,
            service_category_id=service_category_id,
        )
        data = service.get_time_series()
        
        ttl = self._get_cache_ttl(start_date, end_date)
        cache.set(cache_key, data, ttl)
        _audit_analytics(request, "timeseries_view", {"cache": "miss"})
        
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

        service = KpiService(
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
            workbook = build_analytics_workbook(
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
            _audit_analytics(
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
        _audit_analytics(
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


class CacheClearView(APIView):
    """
    Endpoint para limpiar el caché de analytics.
    Solo accesible para admins.
    """
    permission_classes = [IsStaffOrAdmin]

    def post(self, request):
        """
        Limpia el caché de analytics.
        Parámetros opcionales:
        - scope: 'kpis', 'timeseries', 'dashboard', 'all' (default: 'all')
        """
        scope = request.data.get('scope', 'all')

        if scope not in ['kpis', 'timeseries', 'dashboard', 'dataset', 'all']:
            return Response(
                {"error": "Scope inválido. Use: kpis, timeseries, dashboard, dataset, o all"},
                status=400
            )

        cleared_count = 0

        try:
            if scope == 'all':
                # Limpiar todas las claves que empiecen con 'analytics:'
                # Nota: Esto requiere acceso al backend de caché
                from django.core.cache import cache as django_cache

                # Para Redis, podemos usar keys()
                if hasattr(django_cache, 'keys'):
                    keys = django_cache.keys('analytics:*')
                    for key in keys:
                        django_cache.delete(key)
                        cleared_count += 1
                else:
                    # Fallback: limpiar todo el caché
                    django_cache.clear()
                    cleared_count = -1  # Indicador de limpieza total

            else:
                # Limpiar solo el scope específico
                from django.core.cache import cache as django_cache

                if hasattr(django_cache, 'keys'):
                    pattern = f'analytics:{scope}:*'
                    keys = django_cache.keys(pattern)
                    for key in keys:
                        django_cache.delete(key)
                        cleared_count += 1
                else:
                    return Response(
                        {"error": "El backend de caché no soporta limpieza selectiva. Use scope='all'"},
                        status=400
                    )

            _audit_analytics(
                request,
                "cache_cleared",
                {"scope": scope, "cleared_count": cleared_count}
            )

            message = f"Caché limpiado exitosamente"
            if cleared_count >= 0:
                message += f": {cleared_count} claves eliminadas"

            return Response({
                "success": True,
                "message": message,
                "scope": scope,
                "cleared_count": cleared_count if cleared_count >= 0 else "all"
            })

        except Exception as e:
            return Response(
                {"error": f"Error limpiando caché: {str(e)}"},
                status=500
            )


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [CanViewAnalytics]
    CACHE_TTL = 300  # Aumentado a 5 minutos

    def list(self, request):
        return Response({"detail": "Usa las acciones del dashboard."})

    def _today(self):
        return timezone.localdate()

    @staticmethod
    def _user_payload(user):
        if not user:
            return {}
        return {
            "id": str(user.id),
            "name": user.get_full_name(),
            "phone": user.phone_number,
            "email": user.email,
        }

    def _cache_key(self, request, suffix):
        role = getattr(request.user, "role", "ANON")
        return f"analytics:dashboard:{role}:{suffix}"

    @action(detail=False, methods=["get"], url_path="agenda-today")
    def agenda_today(self, request):
        today = self._today()
        cache_key = self._cache_key(request, f"agenda:{today.isoformat()}")
        cached = cache.get(cache_key)
        
        # Nota: La paginación complica el caching de la lista completa vs paginada.
        # Si cacheamos la lista completa, paginamos después.
        
        if cached is not None:
            _audit_analytics(
                request,
                "dashboard_agenda_today",
                {"date": today.isoformat(), "cache": "hit"},
            )
            # Si está cacheado, asumimos que es la lista completa de dicts
            # Necesitamos re-hidratar o paginar la lista de dicts
            from rest_framework.pagination import PageNumberPagination
            class DashboardPagination(PageNumberPagination):
                page_size = 50
                max_page_size = 100
            
            paginator = DashboardPagination()
            # Paginator espera un queryset o lista
            page = paginator.paginate_queryset(cached, request)
            return paginator.get_paginated_response(page)

        appointments = (
            Appointment.objects.select_related("user", "staff_member")
            .filter(start_time__date=today)
            .order_by("start_time")
        )
        data = []
        for appointment in appointments:
            user = appointment.user
            data.append(
                {
                    "appointment_id": str(appointment.id),
                    "start_time": appointment.start_time.isoformat(),
                    "status": appointment.status,
                    "client": self._user_payload(user),
                    "staff": self._user_payload(appointment.staff_member),
                    "has_debt": getattr(user, "has_pending_final_payment", lambda: False)(),
                }
            )
        
        cache.set(cache_key, data, self.CACHE_TTL)
        _audit_analytics(
            request,
            "dashboard_agenda_today",
            {"date": today.isoformat(), "cache": "miss"},
        )
        
        # Paginación
        from rest_framework.pagination import PageNumberPagination
        class DashboardPagination(PageNumberPagination):
            page_size = 50
            max_page_size = 100
            
        paginator = DashboardPagination()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)

    @action(detail=False, methods=["get"], url_path="pending-payments")
    def pending_payments(self, request):
        cache_key = self._cache_key(request, "pending")
        cached = cache.get(cache_key)
        if cached is not None:
            _audit_analytics(
                request,
                "dashboard_pending_payments",
                {"cache": "hit"},
            )
            return Response({"results": cached})
        pending_payments = Payment.objects.select_related("user").filter(
            status=Payment.PaymentStatus.PENDING
        )
        payment_filter = Q(
            payments__payment_type__in=[
                Payment.PaymentType.ADVANCE,
                Payment.PaymentType.FINAL,
            ]
        ) & Q(
            payments__status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ]
        )
        pending_appointments = (
            Appointment.objects.select_related("user")
            .filter(status=Appointment.AppointmentStatus.PAID)
            .annotate(
                paid_amount=Coalesce(
                    Sum("payments__amount", filter=payment_filter),
                    Decimal("0"),
                )
            )
            .order_by("-start_time")
        )
        payments_payload = [
            {
                "type": "payment",
                "payment_id": str(payment.id),
                "amount": float(payment.amount),
                "user": self._user_payload(payment.user),
                "created_at": payment.created_at.isoformat(),
            }
            for payment in pending_payments
        ]
        appointments_payload = [
            {
                "type": "appointment",
                "appointment_id": str(appointment.id),
                "user": self._user_payload(appointment.user),
                "start_time": appointment.start_time.isoformat(),
                "amount_due": float(
                    max(
                        (appointment.price_at_purchase or Decimal("0")) - (appointment.paid_amount or Decimal("0")),
                        Decimal("0"),
                    )
                ),
            }
            for appointment in pending_appointments
        ]
        combined = payments_payload + appointments_payload
        cache.set(cache_key, combined, self.CACHE_TTL)
        _audit_analytics(
            request,
            "dashboard_pending_payments",
            {"cache": "miss"},
        )
        return Response({"results": combined})

    @action(detail=False, methods=["get"], url_path="expiring-credits")
    def expiring_credits(self, request):
        today = self._today()
        upcoming = today + timedelta(days=7)
        cache_key = self._cache_key(request, f"credits:{today.isoformat()}")
        cached = cache.get(cache_key)
        if cached is not None:
            _audit_analytics(
                request,
                "dashboard_expiring_credits",
                {"date": today.isoformat(), "cache": "hit"},
            )
            return Response({"results": cached})
        credits = ClientCredit.objects.select_related("user").filter(
            expires_at__gte=today,
            expires_at__lte=upcoming,
            status__in=[
                ClientCredit.CreditStatus.AVAILABLE,
                ClientCredit.CreditStatus.PARTIALLY_USED,
            ],
        )
        results = [
            {
                "credit_id": str(credit.id),
                "user": self._user_payload(credit.user),
                "remaining_amount": float(credit.remaining_amount),
                "expires_at": credit.expires_at.isoformat(),
            }
            for credit in credits
        ]
        cache.set(cache_key, results, self.CACHE_TTL)
        _audit_analytics(
            request,
            "dashboard_expiring_credits",
            {"date": today.isoformat(), "cache": "miss"},
        )
        return Response({"results": results})

    @action(detail=False, methods=["get"], url_path="renewals")
    def renewals(self, request):
        today = self._today()
        upcoming = today + timedelta(days=7)
        users = CustomUser.objects.filter(
            role=CustomUser.Role.VIP,
            vip_expires_at__gte=today,
            vip_expires_at__lte=upcoming,
        ).order_by("vip_expires_at")
        results = [
            {
                "user": self._user_payload(user),
                "vip_expires_at": user.vip_expires_at.isoformat() if user.vip_expires_at else None,
                "auto_renew": getattr(user, "vip_auto_renew", False),
            }
            for user in users
        ]
        _audit_analytics(
            request,
            "dashboard_renewals",
            {"date": today.isoformat()},
        )
        return Response({"results": results})


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
        return KpiService(start_date, end_date, staff_id=staff_id, service_category_id=service_category_id)

    @action(detail=False, methods=["get"])
    def heatmap(self, request):
        service = self._get_service(request)
        data = service.get_heatmap_data()
        return Response(data)

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        service = self._get_service(request)
        data = service.get_staff_leaderboard()
        return Response(data)

    @action(detail=False, methods=["get"])
    def funnel(self, request):
        service = self._get_service(request)
        data = service.get_funnel_metrics()
        return Response(data)


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
        return KpiService(start_date, end_date, staff_id=staff_id, service_category_id=service_category_id)

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
