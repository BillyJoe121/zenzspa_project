"""
Views Shared - Utilidades comunes para vistas de Analytics.
"""
from datetime import datetime, timedelta
from uuid import UUID

from django.utils import timezone

from users.models import CustomUser


def audit_analytics(request, action, extra=None):
    from core.models import AuditLog
    from core.utils import safe_audit_log
    safe_audit_log(
        action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
        admin_user=getattr(request, "user", None),
        details={
            "analytics_action": action,
            **(extra or {}),
        },
    )


def build_kpi_service(*args, **kwargs):
    from analytics.services import KpiService
    return KpiService(*args, **kwargs)


def build_workbook(*args, **kwargs):
    from analytics.utils import build_analytics_workbook
    return build_analytics_workbook(*args, **kwargs)


class DateFilterMixin:
    MAX_RANGE_DAYS = 365
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
            staff_id = UUID(str(staff_id)) if staff_id else None
        except ValueError:
            raise ValueError("staff_id debe ser un UUID válido.")
        try:
            service_category_id = UUID(str(service_category_id)) if service_category_id else None
        except ValueError:
            raise ValueError("service_category_id debe ser un UUID válido.")
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
