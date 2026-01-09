"""
Views de Créditos de Cliente.

Endpoints para gestión de créditos/vouchers:
- ViewSet admin para CRUD de créditos
- ViewSet de cliente para consultar créditos
- Balance de créditos
- Preview de aplicación de créditos
- Historial de pagos
"""
import logging
from decimal import Decimal

from django.utils import timezone
from rest_framework import status, viewsets, filters, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from users.permissions import IsAdminUser, IsVerified
from core.models import AuditLog
from finances.models import ClientCredit, Payment
from finances.serializers import ClientCreditAdminSerializer, ClientCreditSerializer, PaymentSerializer


logger = logging.getLogger(__name__)


class ClientCreditAdminViewSet(viewsets.ModelViewSet):
    """
    CRUD administrativo para créditos de clientes.
    Permite ajustar saldo disponible tras reembolsos en efectivo u otros casos.

    Búsqueda: ?search=nombre, teléfono o email del usuario
    Filtros: ?status=AVAILABLE&user=uuid
    Ordenamiento: ?ordering=-expires_at
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = ClientCreditAdminSerializer
    queryset = ClientCredit.objects.select_related("user", "originating_payment").order_by("-created_at")

    # Configuración de búsqueda y filtros
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__phone_number',
        'user__email'
    ]
    filterset_fields = ['status', 'user']
    ordering_fields = ['created_at', 'expires_at', 'remaining_amount', 'initial_amount']

    def _compute_status(self, credit: ClientCredit) -> str:
        # Marcar expirado si la fecha ya pasó
        if credit.expires_at and credit.expires_at < timezone.now().date():
            return ClientCredit.CreditStatus.EXPIRED
        if credit.remaining_amount == 0:
            return ClientCredit.CreditStatus.USED
        if credit.remaining_amount < credit.initial_amount:
            return ClientCredit.CreditStatus.PARTIALLY_USED
        return ClientCredit.CreditStatus.AVAILABLE

    def perform_create(self, serializer):
        credit = serializer.save()
        credit.status = self._compute_status(credit)
        credit.save(update_fields=["status"])
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=credit.user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=f"Crédito manual creado: {credit.remaining_amount} - expira {credit.expires_at or 'sin expiración'}",
        )
        return credit

    def perform_update(self, serializer):
        credit = serializer.save()
        new_status = self._compute_status(credit)
        if credit.status != new_status:
            credit.status = new_status
            credit.save(update_fields=["status"])
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=credit.user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=f"Crédito actualizado: saldo {credit.remaining_amount} / inicial {credit.initial_amount}, estado {credit.status}",
        )
        return credit


class ClientCreditViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vista de solo lectura para que los clientes consulten sus créditos/vouchers.
    """
    serializer_class = ClientCreditSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ClientCredit.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['get'], url_path='my')
    def my_credits(self, request):
        """
        Endpoint de conveniencia para compatibilidad con la estructura solicitada:
        GET /api/v1/vouchers/my/
        """
        return self.list(request)


class PaymentHistoryView(generics.ListAPIView):
    """
    Lista el historial de pagos del usuario autenticado.
    
    GET /api/finances/payments/my/
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')


class ClientCreditBalanceView(APIView):
    """
    Retorna el saldo total de créditos activos disponibles para el usuario autenticado.

    GET /api/v1/finances/credits/balance/
    Response: { "balance": 150000.00 }
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request):
        active_credits = ClientCredit.objects.filter(
            user=request.user,
            status__in=[
                ClientCredit.CreditStatus.AVAILABLE,
                ClientCredit.CreditStatus.PARTIALLY_USED
            ],
            expires_at__gte=timezone.now().date()
        )
        total_balance = sum(c.remaining_amount for c in active_credits)

        return Response({
            'balance': total_balance,
            'currency': 'COP'
        })


class CreditPaymentPreviewView(APIView):
    """
    Retorna un preview de cómo se aplicarían los créditos a un monto específico.

    POST /api/v1/finances/credits/preview/
    Body: {
        "amount": 100000
    }

    Response: {
        "original_amount": "100000.00",
        "available_credits": "40000.00",
        "credits_to_use": "40000.00",
        "final_amount": "60000.00",
        "fully_covered": false,
        "currency": "COP"
    }
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def post(self, request):
        # Validar el monto
        amount = request.data.get('amount')
        if not amount:
            return Response(
                {"error": "El campo 'amount' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= Decimal('0'):
                return Response(
                    {"error": "El monto debe ser mayor a cero."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, ArithmeticError):
            return Response(
                {"error": "Monto inválido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calcular saldo disponible del usuario
        active_credits = ClientCredit.objects.filter(
            user=request.user,
            status__in=[
                ClientCredit.CreditStatus.AVAILABLE,
                ClientCredit.CreditStatus.PARTIALLY_USED
            ],
            expires_at__gte=timezone.now().date()
        ).order_by('created_at')

        total_available = sum(c.remaining_amount for c in active_credits)

        # Calcular cuánto se usaría
        credits_to_use = min(amount_decimal, total_available)
        final_amount = max(Decimal('0'), amount_decimal - credits_to_use)
        fully_covered = final_amount <= Decimal('0')

        return Response({
            'original_amount': str(amount_decimal),
            'available_credits': str(total_available),
            'credits_to_use': str(credits_to_use),
            'final_amount': str(final_amount),
            'fully_covered': fully_covered,
            'currency': 'COP'
        })
