from decimal import Decimal

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin
from core.models import GlobalSettings
from .services import DeveloperCommissionService, WompiDisbursementClient
from .models import CommissionLedger
from .serializers import CommissionLedgerSerializer
from .gateway import WompiPaymentClient


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
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        return queryset


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
        }
        return Response(data)


class PSEFinancialInstitutionsView(APIView):
    """
    Lista las instituciones financieras disponibles para PSE.

    GET /api/finances/pse-banks/

    Response:
        {
            "data": [
                {
                    "financial_institution_code": "1022",
                    "financial_institution_name": "BANCO UNION COLOMBIANO"
                },
                ...
            ]
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client = WompiPaymentClient()
        try:
            institutions_data, status_code = client.get_pse_financial_institutions()

            if status_code == 200:
                return Response(institutions_data, status=200)
            else:
                return Response(
                    {"error": "No se pudieron obtener los bancos PSE"},
                    status=status_code
                )
        except Exception as e:
            return Response(
                {"error": f"Error al consultar bancos PSE: {str(e)}"},
                status=500
            )
