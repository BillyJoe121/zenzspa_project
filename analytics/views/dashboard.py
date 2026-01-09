"""
Views Dashboard - Endpoints del dashboard administrativo.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from spa.models import Appointment, ClientCredit, Payment
from users.models import CustomUser

from analytics.permissions import CanViewAnalytics
from analytics.views.shared import audit_analytics


class DashboardPagination(PageNumberPagination):
    """Paginación para el dashboard con page_size de 50"""
    page_size = 50
    max_page_size = 100


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [CanViewAnalytics]
    pagination_class = DashboardPagination
    CACHE_TTL = 300  # 5 minutos

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
    def agenda_week(self, request):
        """
        Retorna el número de citas agendadas para la semana en curso (Lunes a Domingo).
        Excluye las canceladas.
        """
        today = self._today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        cache_key = self._cache_key(request, f"agenda_week:{start_of_week.isoformat()}")
        cached = cache.get(cache_key)

        # Soporte para limpiar caché si es necesario
        if request.query_params.get('force_refresh') == 'true':
            cached = None

        if cached is not None:
            audit_analytics(request, "dashboard_agenda_week", {"cache": "hit"})
            return Response(cached)

        # Contar citas de la semana que no estén canceladas
        count = Appointment.objects.filter(
            start_time__date__gte=start_of_week,
            start_time__date__lte=end_of_week
        ).exclude(
            status=Appointment.AppointmentStatus.CANCELLED
        ).count()

        data = {"count": count, "start_of_week": start_of_week, "end_of_week": end_of_week}
        cache.set(cache_key, data, self.CACHE_TTL)
        audit_analytics(request, "dashboard_agenda_week", {"cache": "miss"})
        return Response(data)

    @action(detail=False, methods=["get"], url_path="pending-payments")
    def pending_payments(self, request):
        """
        Retorna el número de citas con saldo pendiente (outstanding > 0), sin importar su estado.
        """
        cache_key = self._cache_key(request, "pending_count")
        cached = cache.get(cache_key)
        if request.query_params.get('force_refresh') == 'true':
            cached = None

        if cached is not None:
            audit_analytics(request, "dashboard_pending_payments", {"cache": "hit"})
            return Response(cached)

        # Filtro para sumar solo pagos aprobados o con crédito
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

        # Contar citas donde el precio > pagado
        # Nota: Usamos una subquery o lógica simple.
        # Para evitar complejidad excesiva en count(), filtramos por outstanding > 0
        from django.db.models import F

        pending_count = (
            Appointment.objects
            .annotate(
                paid_amount=Coalesce(
                    Sum("payments__amount", filter=payment_filter),
                    Decimal("0"),
                )
            )
            .annotate(
                outstanding=F("price_at_purchase") - F("paid_amount")
            )
            .filter(outstanding__gt=0)
            .count()
        )

        data = {"count": pending_count}
        cache.set(cache_key, data, self.CACHE_TTL)
        audit_analytics(request, "dashboard_pending_payments", {"cache": "miss"})
        return Response(data)

    @action(detail=False, methods=["get"], url_path="expiring-credits")
    def active_credits(self, request):
        """
        Retorna el número total de créditos vigentes (AVAILABLE o PARTIALLY_USED),
        sin importar cuándo vencen.
        """
        cache_key = self._cache_key(request, "active_credits_count")
        cached = cache.get(cache_key)

        if request.query_params.get('force_refresh') == 'true':
            cached = None

        if cached is not None:
            audit_analytics(request, "dashboard_active_credits", {"cache": "hit"})
            return Response(cached)

        today = self._today()

        # Contar créditos válidos
        # Se asume que expirados tienen status=EXPIRED o expires_at < today
        count = ClientCredit.objects.filter(
            status__in=[
                ClientCredit.CreditStatus.AVAILABLE,
                ClientCredit.CreditStatus.PARTIALLY_USED
            ],
            # Asegurarnos de no contar los vencidos por fecha si el status no se actualizó job
            expires_at__gte=today
        ).count()

        data = {"count": count}
        cache.set(cache_key, data, self.CACHE_TTL)
        audit_analytics(request, "dashboard_active_credits", {"cache": "miss"})
        return Response(data)

    @action(detail=False, methods=["get"], url_path="renewals")
    def vip_ratio(self, request):
        """
        Retorna la relación de clientes VIP vs Total Clientes.
        Formato: { "vip_count": X, "total_count": Y }
        """
        cache_key = self._cache_key(request, "vip_ratio")
        cached = cache.get(cache_key)

        if request.query_params.get('force_refresh') == 'true':
            cached = None

        if cached is not None:
            audit_analytics(request, "dashboard_vip_ratio", {"cache": "hit"})
            return Response(cached)

        # Total clientes (excluyendo staff/admin si se desea, aquí contamos roles de cliente)
        # Asumimos que cualquier usuario puede ser cliente, o filtramos por rol si es estricto
        # Vamos a contar todos los usuarios activos
        total_count = CustomUser.objects.filter(is_active=True).exclude(is_superuser=True).count()

        # Total VIP
        vip_count = CustomUser.objects.filter(
            role=CustomUser.Role.VIP,
            is_active=True
        ).count()

        data = {
            "vip_count": vip_count,
            "total_count": total_count,
            "formatted": f"{vip_count}/{total_count}"
        }

        cache.set(cache_key, data, self.CACHE_TTL)
        audit_analytics(request, "dashboard_vip_ratio", {"cache": "miss"})
        return Response(data)
