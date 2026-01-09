"""
Views de Comisiones del Desarrollador.

Endpoints para gestión del libro de comisiones:
- Lista y detalle de asientos
- Desgloses por tipo y método de pago
- Estado de deuda del desarrollador
- Pago manual de comisiones
"""
import uuid
import logging
from decimal import Decimal

from django.db import transaction, models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin, IsSuperAdmin
from core.models import GlobalSettings
from finances.models import CommissionLedger, Payment
from finances.serializers import CommissionLedgerSerializer
from finances.services import DeveloperCommissionService, WompiDisbursementClient


logger = logging.getLogger(__name__)


class CommissionLedgerListView(generics.ListAPIView):
    """
    Lista los asientos del libro de comisiones para conciliación.
    Permite filtrar por estado y rango de fechas.
    """

    serializer_class = CommissionLedgerSerializer
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]
    queryset = CommissionLedger.objects.select_related("source_payment").order_by("-created_at")

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtro por estado
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        # Filtro por tipo de pago (ADVANCE, FINAL, PACKAGE, etc.)
        payment_type = self.request.query_params.get("payment_type")
        if payment_type:
            queryset = queryset.filter(payment_type=payment_type)

        # Filtro por método de pago (CASH, CARD, PSE, NEQUI, etc.)
        payment_method = self.request.query_params.get("payment_method")
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        # Filtro por rango de fechas
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        return queryset


class CommissionLedgerDetailView(generics.RetrieveAPIView):
    """
    Detalle de un asiento de comisión.
    """
    queryset = CommissionLedger.objects.select_related("source_payment")
    serializer_class = CommissionLedgerSerializer
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]


class CommissionBreakdownByTypeView(APIView):
    """
    Retorna un desglose de comisiones agrupadas por tipo de pago.

    GET /api/v1/finances/commissions/breakdown-by-type/

    Query params opcionales:
    - status: filtrar por estado (PENDING, PAID)
    - start_date: fecha de inicio (YYYY-MM-DD)
    - end_date: fecha de fin (YYYY-MM-DD)

    Response:
    {
        "breakdown": [
            {
                "payment_type": "ADVANCE",
                "count": 5,
                "total_amount": "25000.00",
                "paid_amount": "0.00",
                "pending_amount": "25000.00"
            },
            ...
        ],
        "total_count": 10,
        "total_amount": "50000.00"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        queryset = CommissionLedger.objects.all()

        # Aplicar filtros
        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        # Agrupar por payment_type
        breakdown = queryset.values('payment_type').annotate(
            count=models.Count('id'),
            total_amount=Coalesce(Sum('amount'), Decimal('0')),
            paid_amount=Coalesce(Sum('paid_amount'), Decimal('0')),
        ).order_by('-total_amount')

        # Calcular pending_amount para cada grupo
        breakdown_data = []
        total_count = 0
        total_amount = Decimal('0')

        for item in breakdown:
            pending = item['total_amount'] - item['paid_amount']
            breakdown_data.append({
                'payment_type': item['payment_type'] or 'UNKNOWN',
                'count': item['count'],
                'total_amount': str(item['total_amount']),
                'paid_amount': str(item['paid_amount']),
                'pending_amount': str(pending),
            })
            total_count += item['count']
            total_amount += item['total_amount']

        return Response({
            'breakdown': breakdown_data,
            'total_count': total_count,
            'total_amount': str(total_amount),
        })


class CommissionBreakdownByMethodView(APIView):
    """
    Retorna un desglose de comisiones agrupadas por método de pago.

    GET /api/v1/finances/commissions/breakdown-by-method/

    Query params opcionales:
    - status: filtrar por estado (PENDING, PAID)
    - start_date: fecha de inicio (YYYY-MM-DD)
    - end_date: fecha de fin (YYYY-MM-DD)

    Response:
    {
        "breakdown": [
            {
                "payment_method": "CASH",
                "count": 3,
                "total_amount": "15000.00",
                "paid_amount": "0.00",
                "pending_amount": "15000.00"
            },
            ...
        ],
        "total_count": 10,
        "total_amount": "50000.00"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        queryset = CommissionLedger.objects.all()

        # Aplicar filtros
        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        # Agrupar por payment_method
        breakdown = queryset.values('payment_method').annotate(
            count=models.Count('id'),
            total_amount=Coalesce(Sum('amount'), Decimal('0')),
            paid_amount=Coalesce(Sum('paid_amount'), Decimal('0')),
        ).order_by('-total_amount')

        # Calcular pending_amount para cada grupo
        breakdown_data = []
        total_count = 0
        total_amount = Decimal('0')

        for item in breakdown:
            pending = item['total_amount'] - item['paid_amount']
            breakdown_data.append({
                'payment_method': item['payment_method'] or 'UNKNOWN',
                'count': item['count'],
                'total_amount': str(item['total_amount']),
                'paid_amount': str(item['paid_amount']),
                'pending_amount': str(pending),
            })
            total_count += item['count']
            total_amount += item['total_amount']

        return Response({
            'breakdown': breakdown_data,
            'total_count': total_count,
            'total_amount': str(total_amount),
        })


class DeveloperCommissionStatusView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        settings_obj = GlobalSettings.load()
        debt = DeveloperCommissionService.get_developer_debt()
        balance_str = "0.00"
        client = WompiDisbursementClient()
        try:
            balance = client.get_available_balance()
            balance_str = str(balance.quantize(Decimal("0.01")))
        except Exception:
            balance_str = "0.00"
        # Calcular total recaudado (Ventas Totales)
        total_collected = Payment.objects.filter(
            status=Payment.PaymentStatus.APPROVED
        ).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0'))
        )['total']

        data = {
            "developer_debt": str(debt),
            "payout_threshold": str(settings_obj.developer_payout_threshold),
            "developer_in_default": settings_obj.developer_in_default,
            "developer_default_since": (
                settings_obj.developer_default_since.isoformat()
                if settings_obj.developer_default_since
                else None
            ),
            "wompi_available_balance": balance_str,
            "total_collected": str(total_collected),
        }
        return Response(data)


class ManualDeveloperPayoutView(APIView):
    """
    Permite al SuperAdmin marcar la deuda del desarrollador como pagada manualmente
    (ej. pago externo por transferencia bancaria directa).
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @transaction.atomic
    def post(self, request):
        amount = request.data.get("amount")
        if not amount:
            return Response(
                {"error": "Se requiere un monto (amount)."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                raise ValueError("El monto debe ser positivo.")
        except Exception:
            return Response(
                {"error": "Monto inválido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Usar el servicio para aplicar el pago, usando un ID ficticio para transfer_id
        # ya que es un pago manual externo.
        manual_ref = f"MANUAL-{uuid.uuid4().hex[:8]}"
        
        DeveloperCommissionService._apply_payout_to_ledger(
            amount_to_pay=amount_decimal,
            transfer_id=manual_ref,
            performed_by=request.user
        )

        settings_obj = GlobalSettings.load()
        DeveloperCommissionService._exit_default(settings_obj)

        remaining_debt = DeveloperCommissionService.get_developer_debt()
        
        return Response({
            "status": "success",
            "message": f"Se ha registrado el pago manual de {amount_decimal}.",
            "reference": manual_ref,
            "remaining_debt": str(remaining_debt)
        })
