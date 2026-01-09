"""
Views de Analytics de Finanzas - Servicios (Appointments).

Endpoints para estadísticas de servicios/citas:
- Ingresos mensuales de servicios
- Citas completadas
- Distribución de estados para gráficas
"""
import logging
from datetime import datetime
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from dateutil.relativedelta import relativedelta

from users.permissions import IsStaffOrAdmin
from spa.models import Appointment
from finances.models import Payment


logger = logging.getLogger(__name__)


class ServicesRevenueView(APIView):
    """
    Retorna ingresos mensuales SOLO de servicios (appointments).

    GET /api/v1/finances/services/revenue/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "total_revenue": "5450000.00",
        "advance_payments": "2180000.00",
        "final_payments": "3270000.00",
        "cash_payments": "820000.00",
        "online_payments": "4630000.00"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        # Parsear mes
        month_param = request.query_params.get('month')
        if month_param:
            try:
                month_date = datetime.strptime(month_param, '%Y-%m').date()
            except ValueError:
                return Response(
                    {"error": "Formato inválido para month. Usa YYYY-MM."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            month_date = timezone.now().date().replace(day=1)

        # Calcular rango del mes
        month_start = month_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timezone.timedelta(days=1)

        # Filtrar pagos de servicios (ADVANCE y FINAL)
        payments_qs = Payment.objects.filter(
            payment_type__in=[Payment.PaymentType.ADVANCE, Payment.PaymentType.FINAL],
            status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT],
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        )

        # Aggregations
        stats = payments_qs.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0')),
            advance=Coalesce(
                Sum('amount', filter=Q(payment_type=Payment.PaymentType.ADVANCE)),
                Decimal('0')
            ),
            final=Coalesce(
                Sum('amount', filter=Q(payment_type=Payment.PaymentType.FINAL)),
                Decimal('0')
            ),
            cash=Coalesce(
                Sum('amount', filter=Q(payment_method_type='CASH')),
                Decimal('0')
            ),
            online=Coalesce(
                Sum('amount', filter=~Q(payment_method_type='CASH')),
                Decimal('0')
            )
        )

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'total_revenue': str(stats['total']),
            'advance_payments': str(stats['advance']),
            'final_payments': str(stats['final']),
            'cash_payments': str(stats['cash']),
            'online_payments': str(stats['online'])
        })


class ServicesCompletedAppointmentsView(APIView):
    """
    Retorna cantidad de citas finalizadas en el mes.

    GET /api/v1/finances/services/completed-appointments/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "count": 142,
        "total_revenue": "4230000.00"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        # Parsear mes
        month_param = request.query_params.get('month')
        if month_param:
            try:
                month_date = datetime.strptime(month_param, '%Y-%m').date()
            except ValueError:
                return Response(
                    {"error": "Formato inválido para month. Usa YYYY-MM."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            month_date = timezone.now().date().replace(day=1)

        # Calcular rango del mes
        month_start = month_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timezone.timedelta(days=1)

        # Contar citas completadas en el mes (basado en updated_at)
        completed = Appointment.objects.filter(
            status=Appointment.AppointmentStatus.COMPLETED,
            updated_at__date__gte=month_start,
            updated_at__date__lte=month_end
        ).aggregate(
            count=Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'count': completed['count'],
            'total_revenue': str(completed['revenue'])
        })


class ServicesStatusDistributionView(APIView):
    """
    Retorna distribución de servicios para gráfica pastel.

    Categorías:
    - Servicios pagados y finalizados (COMPLETED)
    - Servicios confirmados futuros (CONFIRMED/FULLY_PAID con fecha futura)
    - Servicios en limbo (CONFIRMED/RESCHEDULED/FULLY_PAID con fecha pasada)
    - Servicios cancelados (CANCELLED)

    GET /api/v1/finances/services/status-distribution/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "distribution": {
            "completed_paid": {
                "count": 142,
                "revenue": "4230000.00",
                "label": "Servicios Pagados y Finalizados"
            },
            "confirmed_future": {
                "count": 38,
                "revenue": "1140000.00",
                "label": "Servicios Confirmados Futuros"
            },
            "limbo": {
                "count": 7,
                "revenue": "210000.00",
                "label": "Servicios en Limbo"
            },
            "cancelled": {
                "count": 12,
                "revenue": "360000.00",
                "label": "Servicios Cancelados"
            }
        }
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        # Parsear mes
        month_param = request.query_params.get('month')
        if month_param:
            try:
                month_date = datetime.strptime(month_param, '%Y-%m').date()
            except ValueError:
                return Response(
                    {"error": "Formato inválido para month. Usa YYYY-MM."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            month_date = timezone.now().date().replace(day=1)

        # Calcular rango del mes
        month_start = month_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timezone.timedelta(days=1)
        today = timezone.now().date()

        # Base queryset: citas del mes
        base_qs = Appointment.objects.filter(
            start_time__date__gte=month_start,
            start_time__date__lte=month_end
        )

        # 1. Servicios completados y pagados
        completed_paid = base_qs.filter(
            status=Appointment.AppointmentStatus.COMPLETED
        ).aggregate(
            count=Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        # 2. Servicios confirmados futuros (fecha de mañana en adelante)
        confirmed_future = base_qs.filter(
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.FULLY_PAID
            ],
            start_time__date__gt=today
        ).aggregate(
            count=Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        # 3. Servicios en limbo (fecha ya pasó pero no se completaron ni cancelaron)
        limbo = base_qs.filter(
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.RESCHEDULED,
                Appointment.AppointmentStatus.FULLY_PAID
            ],
            start_time__date__lt=today
        ).aggregate(
            count=Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        # 4. Servicios cancelados
        cancelled = base_qs.filter(
            status=Appointment.AppointmentStatus.CANCELLED
        ).aggregate(
            count=Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'distribution': {
                'completed_paid': {
                    'count': completed_paid['count'],
                    'revenue': str(completed_paid['revenue']),
                    'label': 'Servicios Pagados y Finalizados'
                },
                'confirmed_future': {
                    'count': confirmed_future['count'],
                    'revenue': str(confirmed_future['revenue']),
                    'label': 'Servicios Confirmados Futuros'
                },
                'limbo': {
                    'count': limbo['count'],
                    'revenue': str(limbo['revenue']),
                    'label': 'Servicios en Limbo'
                },
                'cancelled': {
                    'count': cancelled['count'],
                    'revenue': str(cancelled['revenue']),
                    'label': 'Servicios Cancelados'
                }
            }
        })
