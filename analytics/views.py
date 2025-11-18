from datetime import datetime, timedelta
import csv
import io

from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from spa.models import Appointment, Payment, ClientCredit
from spa.services import PaymentService
from marketplace.models import Order
from users.models import CustomUser
from .services import KpiService
from .utils import build_analytics_workbook


class DateFilterMixin:
    def _parse_dates(self, request):
        today = timezone.localdate()
        default_start = today - timedelta(days=6)

        def parse_param(name, default):
            value = request.query_params.get(name)
            if not value:
                return default
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"Formato inválido para {name}. Usa YYYY-MM-DD.")

        start_date = parse_param("start_date", default_start)
        end_date = parse_param("end_date", today)
        if start_date > end_date:
            raise ValueError("start_date debe ser menor o igual a end_date.")
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


class KpiView(DateFilterMixin, APIView):
    """
    Endpoint que entrega los KPIs de negocio en un rango de fechas.
    """

    permission_classes = [IsAuthenticated]

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
        data = service.get_business_kpis()
        data["start_date"] = start_date.isoformat()
        data["end_date"] = end_date.isoformat()
        data["staff_id"] = staff_id
        data["service_category_id"] = service_category_id
        return Response(data)


class AnalyticsExportView(DateFilterMixin, APIView):
    permission_classes = [IsAuthenticated]

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
        export_format = request.query_params.get("format", "csv").lower()
        if export_format == "xlsx":
            kpis = service.get_business_kpis()
            workbook = build_analytics_workbook(
                kpis=kpis,
                sales_details=service.get_sales_details(),
                debt_metrics=kpis.get("debt_recovery", {}),
                debt_rows=service.get_debt_rows(),
                start_date=start_date,
                end_date=end_date,
            )
            filename = f"analytics_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
            response = HttpResponse(
                workbook,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        rows = service.as_rows()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value", "start_date", "end_date"])
        for metric, value in rows:
            writer.writerow([metric, value, start_date.isoformat(), end_date.isoformat()])

        filename = f"analytics_{start_date.isoformat()}_{end_date.isoformat()}.csv"
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    CACHE_TTL = 60

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

    def _cache_key(self, suffix):
        return f"analytics:dashboard:{suffix}"

    @action(detail=False, methods=["get"], url_path="agenda-today")
    def agenda_today(self, request):
        today = self._today()
        cache_key = self._cache_key(f"agenda:{today.isoformat()}")
        cached = cache.get(cache_key)
        if cached is not None:
            return Response({"results": cached})
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
        return Response({"results": data})

    @action(detail=False, methods=["get"], url_path="pending-payments")
    def pending_payments(self, request):
        cache_key = self._cache_key("pending")
        cached = cache.get(cache_key)
        if cached is not None:
            return Response({"results": cached})
        pending_payments = Payment.objects.select_related("user").filter(
            status=Payment.PaymentStatus.PENDING
        )
        pending_appointments = (
            Appointment.objects.select_related("user")
            .filter(status=Appointment.AppointmentStatus.PAID)
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
                "amount_due": float(PaymentService.calculate_outstanding_amount(appointment)),
            }
            for appointment in pending_appointments
        ]
        combined = payments_payload + appointments_payload
        cache.set(cache_key, combined, self.CACHE_TTL)
        return Response({"results": combined})

    @action(detail=False, methods=["get"], url_path="expiring-credits")
    def expiring_credits(self, request):
        today = self._today()
        upcoming = today + timedelta(days=7)
        cache_key = self._cache_key(f"credits:{today.isoformat()}")
        cached = cache.get(cache_key)
        if cached is not None:
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
        return Response({"results": results})
