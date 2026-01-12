"""
Views de Analytics de Finanzas - Marketplace.

Endpoints para estadísticas del marketplace/tienda:
- Ingresos totales mensuales
- Ingresos por producto
- Estadísticas de órdenes
- Ingresos diarios para gráficas
"""
import logging
from datetime import datetime
from decimal import Decimal

from django.db.models import Sum, Count, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from dateutil.relativedelta import relativedelta

from users.permissions import IsStaffOrAdmin
from finances.models import Payment


logger = logging.getLogger(__name__)


class MarketplaceRevenueView(APIView):
    """
    Retorna total vendido en marketplace por mes.

    GET /api/v1/finances/marketplace/revenue/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "total_revenue": "2340000.00",
        "orders_count": 67,
        "average_order_value": "34925.37"
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

        # Filtrar pagos de órdenes aprobados
        payments_stats = Payment.objects.filter(
            payment_type=Payment.PaymentType.ORDER,
            status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT],
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0')),
            count=Count('order_id', distinct=True)
        )

        total_revenue = payments_stats['total']
        orders_count = payments_stats['count']

        # Calcular promedio
        if orders_count > 0:
            average = total_revenue / orders_count
        else:
            average = Decimal('0')

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'total_revenue': str(total_revenue),
            'orders_count': orders_count,
            'average_order_value': str(average.quantize(Decimal('0.01')))
        })


class MarketplaceProductsRevenueView(APIView):
    """
    Retorna ingresos desglosados por producto.

    GET /api/v1/finances/marketplace/products-revenue/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)
    - limit: Límite de productos a retornar (default: 20)

    Response:
    {
        "month": "2026-01",
        "products": [
            {
                "product_id": "uuid-123",
                "product_name": "Crema Facial Hidratante",
                "variant_name": "50ml",
                "quantity_sold": 45,
                "total_revenue": "675000.00"
            },
            ...
        ]
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        from marketplace.models import OrderItem, Order

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

        # Límite de productos
        try:
            limit = int(request.query_params.get('limit', 20))
        except ValueError:
            limit = 20

        # Calcular rango del mes
        month_start = month_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timezone.timedelta(days=1)

        # Obtener items de órdenes pagadas en el mes
        products_data = OrderItem.objects.filter(
            order__status__in=[
                Order.OrderStatus.PAID,
                Order.OrderStatus.PREPARING,
                Order.OrderStatus.SHIPPED,
                Order.OrderStatus.DELIVERED
            ],
            order__created_at__date__gte=month_start,
            order__created_at__date__lte=month_end
        ).values(
            'product_variant__product_id',
            'product_variant__product__name',
            'product_variant__name'
        ).annotate(
            quantity_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('price_at_purchase'))
        ).order_by('-total_revenue')[:limit]

        # Formatear respuesta
        products = [
            {
                'product_id': str(item['product_variant__product_id']),
                'product_name': item['product_variant__product__name'],
                'variant_name': item['product_variant__name'] or 'Predeterminado',
                'quantity_sold': item['quantity_sold'],
                'total_revenue': str(item['total_revenue'])
            }
            for item in products_data
        ]

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'products': products
        })


class MarketplaceOrdersStatsView(APIView):
    """
    Retorna estadísticas generales de órdenes.

    GET /api/v1/finances/marketplace/orders-stats/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "orders_by_status": {
            "paid": 45,
            "preparing": 12,
            "shipped": 8,
            "delivered": 67,
            "cancelled": 3
        },
        "delivery_methods": {
            "pickup": 38,
            "delivery": 22,
            "associate_to_appointment": 7
        },
        "credits_used": "245000.00"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        from marketplace.models import Order

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

        # Base queryset
        base_qs = Order.objects.filter(
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        )

        # Órdenes por estado
        orders_by_status_raw = base_qs.values('status').annotate(
            count=Count('id')
        )
        orders_by_status = {item['status'].lower(): item['count'] for item in orders_by_status_raw}

        # Métodos de entrega
        delivery_methods_raw = base_qs.values('delivery_option').annotate(
            count=Count('id')
        )
        delivery_methods = {item['delivery_option'].lower(): item['count'] for item in delivery_methods_raw}

        # Créditos usados en órdenes
        credits_used = Payment.objects.filter(
            payment_type=Payment.PaymentType.ORDER,
            status=Payment.PaymentStatus.PAID_WITH_CREDIT,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'orders_by_status': orders_by_status,
            'delivery_methods': delivery_methods,
            'credits_used': str(credits_used['total'])
        })


class MarketplaceDailyRevenueView(APIView):
    """
    Retorna ingresos diarios de marketplace para gráficas.

    GET /api/v1/finances/marketplace/daily-revenue/

    Query params:
    - month: Mes en formato YYYY-MM (default: mes actual)

    Response:
    {
        "month": "2026-01",
        "daily_data": [
            {"date": "2026-01-01", "revenue": "45000.00", "orders": 3},
            {"date": "2026-01-02", "revenue": "67500.00", "orders": 5},
            ...
        ]
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

        # Agrupar por día
        daily_stats = Payment.objects.filter(
            payment_type=Payment.PaymentType.ORDER,
            status__in=[Payment.PaymentStatus.APPROVED, Payment.PaymentStatus.PAID_WITH_CREDIT],
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        ).values('created_at__date').annotate(
            revenue=Coalesce(Sum('amount'), Decimal('0')),
            orders=Count('order_id', distinct=True)
        ).order_by('created_at__date')

        # Formatear respuesta
        daily_data = [
            {
                'date': item['created_at__date'].isoformat(),
                'revenue': str(item['revenue']),
                'orders': item['orders']
            }
            for item in daily_stats
        ]

        return Response({
            'month': month_start.strftime('%Y-%m'),
            'daily_data': daily_data
        })
