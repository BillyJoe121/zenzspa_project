"""
Views para el módulo finances.

Incluye endpoints de:
- Comisiones del desarrollador
- Iniciación de pagos (appointments, VIP, packages)
- Webhook de Wompi
- Instituciones financieras PSE
"""
import uuid
import logging
from decimal import Decimal
import requests

from django.conf import settings
from django.db import transaction, models
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminUser, IsStaffOrAdmin, IsVerified
from core.models import AuditLog, GlobalSettings
from spa.models import Appointment
from .services import DeveloperCommissionService, WompiDisbursementClient
from .wompi_payouts_client import WompiPayoutsClient, WompiPayoutsError
from .webhooks_payouts import WompiPayoutsWebhookService
from .models import ClientCredit, CommissionLedger, Payment, PaymentCreditUsage, WebhookEvent
from .serializers import ClientCreditAdminSerializer, CommissionLedgerSerializer, ClientCreditSerializer, PaymentSerializer
from .gateway import WompiPaymentClient, build_integrity_signature
from .webhooks import WompiWebhookService
from spa.serializers import PackagePurchaseCreateSerializer
from .payments import PaymentService

# Logger
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
    from users.permissions import IsSuperAdmin
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
            result = client.get_pse_financial_institutions()

            # La función de gateway devuelve actualmente solo la lista; soporta tuplas por si cambia.
            if isinstance(result, tuple) and len(result) == 2:
                institutions_data, status_code = result
            else:
                institutions_data = result
                status_code = 200

            if status_code == 200:
                return Response(institutions_data, status=200)
            else:
                return Response(
                    {"error": "No se pudieron obtener los bancos PSE"},
                    status=status_code
                )
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response else 502
            return Response(
                {"error": "Error al consultar bancos PSE", "detail": str(exc)},
                status=status_code,
            )
        except Exception as e:
            return Response(
                {"error": f"Error al consultar bancos PSE: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class InitiateAppointmentPaymentView(generics.GenericAPIView):
    """
    Inicia el flujo de pago para una cita.
    
    IMPORTANTE: Este endpoint ahora separa PREVIEW de CONFIRMACIÓN.
    
    GET /api/finances/payments/appointment/<pk>/initiate/

    Query params:
    - payment_type: 'deposit' (default), 'full', o 'balance'
    - use_credits: 'true' o 'false' (default) - Si debe mostrar preview de créditos
    - confirm: 'true' o 'false' (default) - Si debe APLICAR créditos y crear pagos
    
    Comportamiento:
    - Sin confirm=true: Retorna SOLO preview (no modifica nada)
    - Con confirm=true: Aplica créditos, crea pagos, cambia estado de cita
    
    Estados soportados:
    - PENDING_PAYMENT: Puede pagar deposit (40%) o full (100%)
    - CONFIRMED/RESCHEDULED: Puede pagar balance (saldo pendiente)
    """
    permission_classes = [IsAuthenticated, IsVerified]

    def get(self, request, pk):
        appointment = generics.get_object_or_404(Appointment, pk=pk, user=request.user)

        payment_type = request.query_params.get('payment_type', 'deposit')
        use_credits = request.query_params.get('use_credits', 'false').lower() == 'true'
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        total_price = appointment.price_at_purchase

        # Calcular outstanding_balance
        from .payments import PaymentService
        outstanding = PaymentService.calculate_outstanding_amount(appointment)

        # Determinar el monto y tipo de pago según el estado de la cita
        if appointment.status == Appointment.AppointmentStatus.PENDING_PAYMENT:
            # Cita nueva: puede pagar anticipo, total, o saldo (si ya pagó algo)
            if payment_type == 'full':
                amount = total_price
                payment_type_enum = Payment.PaymentType.FINAL
            elif payment_type == 'balance':
                # Pagar saldo pendiente (útil si ya hizo un pago parcial)
                if outstanding <= Decimal('0'):
                    return Response(
                        {"error": "Esta cita no tiene saldo pendiente por pagar."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                amount = outstanding
                payment_type_enum = Payment.PaymentType.FINAL
            else:  # deposit (default)
                # Pago de anticipo (porcentaje configurable)
                global_settings = GlobalSettings.load()
                advance_percentage = Decimal(global_settings.advance_payment_percentage / 100)

                logger.info(
                    "Consultando pago de cita: appointment_id=%s, user=%s, price=%s, advance_pct=%s, confirm=%s",
                    appointment.id, request.user.id, total_price, advance_percentage, confirm
                )

                amount = total_price * advance_percentage
                payment_type_enum = Payment.PaymentType.ADVANCE

        elif appointment.status in [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.RESCHEDULED,
            Appointment.AppointmentStatus.FULLY_PAID,
        ]:
            # Cita confirmada, reagendada o totalmente pagada: solo puede pagar el saldo pendiente
            if outstanding <= Decimal('0'):
                return Response(
                    {"error": "Esta cita no tiene saldo pendiente por pagar."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            amount = outstanding
            payment_type_enum = Payment.PaymentType.FINAL

        else:
            return Response(
                {"error": f"No se puede iniciar pago para citas con estado '{appointment.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ========================================
        # MODO PREVIEW (sin confirm=true)
        # Solo calcula, NO modifica nada
        # ========================================
        if not confirm:
            preview_data = {
                'mode': 'preview',
                'appointmentId': str(appointment.id),
                'appointmentStatus': appointment.status,
                'paymentType': payment_type_enum,
                'totalPrice': str(total_price),
                'selectedAmount': str(amount),
                'outstandingBalance': str(outstanding),
            }
            
            # Si el usuario quiere ver preview de créditos
            if use_credits:
                credit_preview = PaymentService.preview_credits_application(request.user, amount)
                preview_data['creditPreview'] = {
                    'availableCredits': str(credit_preview['available_credits']),
                    'creditsToApply': str(credit_preview['credits_to_apply']),
                    'amountAfterCredits': str(credit_preview['amount_remaining']),
                    'fullyCoveredByCredits': credit_preview['fully_covered'],
                }
            
            return Response(preview_data, status=status.HTTP_200_OK)

        # ========================================
        # MODO CONFIRMACIÓN (con confirm=true)
        # Aplica créditos, crea pagos, modifica estado
        # ========================================
        with transaction.atomic():
            credits_applied = Decimal('0')
            credit_movements = []

            if use_credits:
                credit_result = PaymentService.apply_credits_to_payment(request.user, amount)
                credits_applied = credit_result.credits_applied
                credit_movements = credit_result.credit_movements
                amount_to_pay = credit_result.amount_remaining

                logger.info(
                    "Créditos aplicados a cita (CONFIRM): appointment_id=%s, user=%s, credits_used=%s, remaining=%s",
                    appointment.id, request.user.id, credits_applied, amount_to_pay
                )

                # Si los créditos cubrieron TODO el monto
                if credit_result.fully_covered:
                    # Crear pago completamente cubierto con crédito
                    reference = f"APPT-CREDIT-{appointment.id}-{uuid.uuid4().hex[:8]}"

                    payment = Payment.objects.create(
                        user=request.user,
                        appointment=appointment,
                        amount=credits_applied,
                        payment_type=payment_type_enum,
                        status=Payment.PaymentStatus.PAID_WITH_CREDIT,
                        transaction_id=reference,
                        used_credit=credit_movements[0][0] if credit_movements else None
                    )

                    # Crear registros de uso de crédito
                    PaymentCreditUsage.objects.bulk_create([
                        PaymentCreditUsage(
                            payment=payment,
                            credit=credit,
                            amount=used_amount
                        )
                        for credit, used_amount in credit_movements
                    ])

                    # Actualizar estado de la cita según el tipo de pago
                    new_outstanding = PaymentService.calculate_outstanding_amount(appointment)
                    if new_outstanding <= Decimal('0'):
                        appointment.status = Appointment.AppointmentStatus.FULLY_PAID
                    else:
                        appointment.status = Appointment.AppointmentStatus.CONFIRMED

                    appointment.save(update_fields=['status', 'updated_at'])

                    # Registrar comisión del desarrollador
                    DeveloperCommissionService.handle_successful_payment(payment)

                    # Retornar payload especial indicando que se pagó con crédito
                    return Response({
                        'status': 'paid_with_credit',
                        'paymentId': str(payment.id),
                        'credits_used': str(credits_applied),
                        'amount_paid': '0',
                        'appointmentStatus': appointment.status,
                        'paymentType': payment_type_enum
                    }, status=status.HTTP_200_OK)

                # Si hay créditos parciales, crear primero el pago con crédito
                if credits_applied > 0:
                    credit_payment = Payment.objects.create(
                        user=request.user,
                        appointment=appointment,
                        amount=credits_applied,
                        payment_type=payment_type_enum,
                        status=Payment.PaymentStatus.PAID_WITH_CREDIT,
                        transaction_id=f"APPT-CREDIT-{appointment.id}-{uuid.uuid4().hex[:8]}",
                        used_credit=credit_movements[0][0] if credit_movements else None
                    )

                    # Crear registros de uso de crédito
                    PaymentCreditUsage.objects.bulk_create([
                        PaymentCreditUsage(
                            payment=credit_payment,
                            credit=credit,
                            amount=used_amount
                        )
                        for credit, used_amount in credit_movements
                    ])

                    # Registrar comisión del desarrollador para el pago con crédito
                    DeveloperCommissionService.handle_successful_payment(credit_payment)

                    logger.info(
                        "Pago parcial con crédito creado: appointment_id=%s, payment_id=%s, amount=%s",
                        appointment.id, credit_payment.id, credits_applied
                    )

                # Continuar con el remanente para Wompi
                amount = amount_to_pay
            else:
                # No usar créditos, monto completo
                amount_to_pay = amount

            # Buscar o crear el pago pendiente por el remanente
            try:
                payment = appointment.payments.get(
                    status=Payment.PaymentStatus.PENDING,
                    payment_type=payment_type_enum
                )
                # Actualizar el monto con el remanente después de créditos
                payment.amount = amount
                payment.save()
            except Payment.DoesNotExist:
                # Crear nuevo pago con el tipo correcto
                payment = Payment.objects.create(
                    user=request.user,
                    appointment=appointment,
                    amount=amount,
                    payment_type=payment_type_enum,
                    status=Payment.PaymentStatus.PENDING
                )

            amount_in_cents = int(payment.amount * 100)
            # Generar referencia única por intento para evitar error "La referencia ya ha sido usada"
            suffix = uuid.uuid4().hex[:6]
            reference = f"PAY-{str(payment.id)[-10:]}-{suffix}"
            payment.transaction_id = reference
            payment.save()

            signature = build_integrity_signature(
                reference=reference,
                amount_in_cents=amount_in_cents,
                currency="COP"
            )

            # TEMPORAL: Override redirectUrl para desarrollo local
            redirect_url = settings.WOMPI_REDIRECT_URL
            if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
                redirect_url = 'about:blank'
                logger.warning(
                    "[DEVELOPMENT] Usando 'about:blank' como redirectUrl porque "
                    "WOMPI_REDIRECT_URL contiene localhost: %s", settings.WOMPI_REDIRECT_URL
                )

            payment_data = {
                'publicKey': settings.WOMPI_PUBLIC_KEY,
                'currency': "COP",
                'amountInCents': amount_in_cents,
                'reference': reference,
                'signatureIntegrity': signature,
                'redirectUrl': redirect_url,
                # Campos adicionales para el frontend
                'paymentId': str(payment.id),
                'paymentType': payment_type_enum,
                'appointmentStatus': appointment.status,
            }

            # Si se aplicaron créditos parciales, agregar info al payload
            if use_credits and credits_applied > 0:
                payment_data['credits_used'] = str(credits_applied)
                payment_data['original_amount'] = str(amount + credits_applied)
                payment_data['status'] = 'partial_credit'

            return Response(payment_data, status=status.HTTP_200_OK)


class WompiWebhookView(generics.GenericAPIView):
    """
    Endpoint para recibir webhooks de Wompi.
    Migrado desde spa.views.packages para centralizar lógica de pagos.

    POST /api/finances/webhooks/wompi/
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            webhook_service = WompiWebhookService(request.data, headers=request.headers)
            event_type = webhook_service.event_type

            if event_type == "transaction.updated":
                result = webhook_service.process_transaction_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            if event_type in {"nequi_token.updated", "bancolombia_transfer_token.updated"}:
                result = webhook_service.process_token_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            if event_type in {"transfer.updated", "payout.updated"}:
                result = webhook_service.process_payout_update()
                return Response({"status": "webhook processed", "result": result}, status=status.HTTP_200_OK)
            webhook_service._update_event_status(WebhookEvent.Status.IGNORED, "Evento no manejado.")
            return Response({"status": "event_type_not_handled"}, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Error interno del servidor al procesar el webhook."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WompiManualConfirmView(generics.GenericAPIView):
    """
    Endpoint para confirmar pagos manualmente cuando el widget modal
    no redirige y Wompi no envía webhook (desarrollo local).
    
    POST /api/finances/webhooks/wompi/manual-confirm/
    Body: {
        "transaction_id": "12001854-176712619B-56986",
        "reference": "PAY-396de01fb41",
        "status": "APPROVED"
    }
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transaction_id = request.data.get('transaction_id')
        reference = request.data.get('reference')
        transaction_status = request.data.get('status', 'APPROVED')
        
        if not transaction_id:
            return Response(
                {"error": "transaction_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"[MANUAL-CONFIRM] Confirmando pago: {transaction_id}")
        
        try:
            # Buscar el pago por transaction_id
            # El reference de Wompi se guarda como transaction_id en nuestro modelo
            payment = Payment.objects.filter(transaction_id=reference).first()
            
            if not payment:
                logger.error(f"[MANUAL-CONFIRM] Pago no encontrado con reference: {reference}")
                return Response(
                    {"error": "Pago no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Construir payload simulado de Wompi
            transaction_payload = {
                "id": transaction_id,
                "reference": reference,
                "status": transaction_status,
                "payment_method_type": "CARD",
            }
            
            # Usar PaymentService para aplicar el estado
            # Esto ejecutará toda la lógica: actualizar cita, crear comisión, etc.
            from .payments import PaymentService
            final_status = PaymentService.apply_gateway_status(
                payment=payment,
                gateway_status=transaction_status,
                transaction_payload=transaction_payload
            )
            
            logger.info(f"[MANUAL-CONFIRM] Pago actualizado: {payment.id} -> {final_status}")
            
            return Response({
                "status": "success",
                "payment_id": str(payment.id),
                "payment_status": final_status
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"[MANUAL-CONFIRM] Error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return Response(
                {"error": f"Error al confirmar pago: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InitiateVipSubscriptionView(generics.GenericAPIView):
    """
    Inicia el flujo de pago para suscripción VIP.
    Migrado desde spa.views.packages para centralizar lógica de suscripciones.

    POST /api/finances/payments/vip-subscription/initiate/
    """
    permission_classes = [IsAuthenticated, IsVerified]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        global_settings = GlobalSettings.load()
        vip_price = global_settings.vip_monthly_price

        if vip_price is None or vip_price <= 0:
            return Response(
                {"error": "El precio de la membresía VIP no está configurado en el sistema."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        reference = f"VIP-{user.id}-{uuid.uuid4().hex[:8]}"
        amount_in_cents = int(vip_price * 100)

        Payment.objects.create(
            user=user,
            amount=vip_price,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.VIP_SUBSCRIPTION,
            transaction_id=reference
        )

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        # TEMPORAL: Override redirectUrl para desarrollo local
        redirect_url = settings.WOMPI_REDIRECT_URL
        if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
            redirect_url = 'about:blank'
            logger.warning(
                f"[DEVELOPMENT] VIP: Usando 'about:blank' como redirectUrl"
            )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': redirect_url
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class InitiatePackagePurchaseView(generics.CreateAPIView):
    """
    Inicia el flujo de pago para la compra de un paquete.
    Migrado desde spa.views.packages para centralizar lógica de pagos.
    
    POST /api/finances/payments/package/initiate/
    """
    permission_classes = [IsAuthenticated, IsVerified]
    serializer_class = PackagePurchaseCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        package = serializer.validated_data['package']
        user = request.user

        # Usar el servicio centralizado para crear el pago
        from finances.payments import PaymentService
        payment = PaymentService.create_package_payment(user, package)
        
        amount_in_cents = int(payment.amount * 100)
        reference = payment.transaction_id

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency="COP"
        )

        # TEMPORAL: Override redirectUrl para desarrollo local
        redirect_url = settings.WOMPI_REDIRECT_URL
        if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
            redirect_url = 'about:blank'
            logger.warning(
                f"[DEVELOPMENT] Package: Usando 'about:blank' como redirectUrl"
            )

        payment_data = {
            'publicKey': settings.WOMPI_PUBLIC_KEY,
            'currency': "COP",
            'amountInCents': amount_in_cents,
            'reference': reference,
            'signatureIntegrity': signature,  # Frontend debe usar esto para construir signature:integrity
            'redirectUrl': redirect_url
        }
        return Response(payment_data, status=status.HTTP_200_OK)


class BasePaymentCreationView(APIView):
    """Helper base class para crear transacciones Wompi a partir de un Payment existente."""

    permission_classes = [IsAuthenticated, IsVerified]
    payment_method = None  # override

    def get_payment(self, request, pk):
        try:
            return Payment.objects.get(pk=pk, user=request.user, status=Payment.PaymentStatus.PENDING)
        except Payment.DoesNotExist:
            return None

    def bad_request(self, message):
        return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


class CreatePSEPaymentView(BasePaymentCreationView):
    """Crea transacción PSE server-side."""
    payment_method = "PSE"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        required_fields = [
            "user_type",
            "user_legal_id",
            "user_legal_id_type",
            "financial_institution_code",
            "payment_description",
        ]
        for field in required_fields:
            if not data.get(field):
                return self.bad_request(f"Falta el campo requerido: {field}")

        response_data, status_code = PaymentService.create_pse_payment(
            payment=payment,
            user_type=int(data["user_type"]),
            user_legal_id=str(data["user_legal_id"]),
            user_legal_id_type=str(data["user_legal_id_type"]),
            financial_institution_code=str(data["financial_institution_code"]),
            payment_description=str(data["payment_description"]),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateNequiPaymentView(BasePaymentCreationView):
    """Crea transacción Nequi server-side."""
    payment_method = "NEQUI"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        phone_number = data.get("phone_number")
        if not phone_number:
            return self.bad_request("Falta el campo requerido: phone_number")

        response_data, status_code = PaymentService.create_nequi_payment(
            payment=payment,
            phone_number=str(phone_number),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateDaviplataPaymentView(BasePaymentCreationView):
    """Crea transacción Daviplata server-side."""
    payment_method = "DAVIPLATA"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        phone_number = data.get("phone_number")
        if not phone_number:
            return self.bad_request("Falta el campo requerido: phone_number")

        response_data, status_code = PaymentService.create_daviplata_payment(
            payment=payment,
            phone_number=str(phone_number),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class CreateBancolombiaTransferPaymentView(BasePaymentCreationView):
    """Crea transacción Bancolombia Transfer server-side (botón)."""
    payment_method = "BANCOLOMBIA_TRANSFER"

    def post(self, request, pk):
        payment = self.get_payment(request, pk)
        if not payment:
            return Response({"error": "Pago no encontrado o no está pendiente."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        payment_description = data.get("payment_description")
        if not payment_description:
            return self.bad_request("Falta el campo requerido: payment_description")

        response_data, status_code = PaymentService.create_bancolombia_transfer_payment(
            payment=payment,
            payment_description=str(payment_description),
            redirect_url=data.get("redirect_url"),
            expiration_time=data.get("expiration_time"),
        )
        return Response(response_data, status=status_code)


class ClientCreditAdminViewSet(viewsets.ModelViewSet):
    """
    CRUD administrativo para créditos de clientes.
    Permite ajustar saldo disponible tras reembolsos en efectivo u otros casos.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = ClientCreditAdminSerializer
    queryset = ClientCredit.objects.select_related("user", "originating_payment").order_by("-created_at")

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


# ========================================
# WOMPI PAYOUTS - ENDPOINTS ADMIN
# ========================================

class WompiPayoutsAccountsView(APIView):
    """
    Consulta las cuentas origen disponibles para dispersión en Wompi.

    GET /api/v1/finances/wompi-payouts/accounts/

    Response:
    {
        "accounts": [
            {
                "id": "uuid",
                "balanceInCents": 1000000,
                "accountNumber": "1234567890",
                "bankId": "1007",
                "accountType": "AHORROS",
                "status": "ACTIVE"
            }
        ],
        "mode": "sandbox"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        try:
            client = WompiPayoutsClient()
            accounts = client.get_accounts()

            return Response({
                "accounts": accounts,
                "mode": settings.WOMPI_PAYOUT_MODE,
                "total_accounts": len(accounts)
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando cuentas de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsBanksView(APIView):
    """
    Consulta la lista de bancos soportados por Wompi para dispersión.

    GET /api/v1/finances/wompi-payouts/banks/

    Response:
    {
        "banks": [
            {
                "id": "1007",
                "name": "BANCOLOMBIA",
                "code": "1007"
            },
            ...
        ],
        "total_banks": 50
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        try:
            client = WompiPayoutsClient()
            banks = client.get_banks()

            return Response({
                "banks": banks,
                "total_banks": len(banks)
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando bancos de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsBalanceView(APIView):
    """
    Consulta el saldo disponible en la cuenta de dispersión.

    GET /api/v1/finances/wompi-payouts/balance/

    Query params:
    - account_id (opcional): ID de cuenta específica

    Response:
    {
        "balance": "10000.00",
        "currency": "COP",
        "account_id": "uuid",
        "mode": "sandbox"
    }
    """
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        account_id = request.query_params.get('account_id')

        try:
            client = WompiPayoutsClient()
            balance = client.get_available_balance(account_id=account_id)

            return Response({
                "balance": str(balance),
                "currency": "COP",
                "account_id": account_id or "default",
                "mode": settings.WOMPI_PAYOUT_MODE
            })

        except WompiPayoutsError as exc:
            logger.exception("Error consultando saldo de Wompi Payouts")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsRechargeView(APIView):
    """
    Recarga saldo en cuenta de sandbox (solo para testing).

    POST /api/v1/finances/wompi-payouts/sandbox/recharge/

    Body:
    {
        "account_id": "uuid",
        "amount": "100000.00"
    }

    Response:
    {
        "success": true,
        "account_id": "uuid",
        "amount": "100000.00",
        "message": "Saldo recargado exitosamente"
    }
    """
    permission_classes = [IsAuthenticated, IsAdminUser]  # Solo superadmin

    def post(self, request):
        # Solo permitir en sandbox
        if settings.WOMPI_PAYOUT_MODE != "sandbox":
            return Response(
                {"error": "La recarga de saldo solo está disponible en modo sandbox"},
                status=status.HTTP_403_FORBIDDEN
            )

        account_id = request.data.get('account_id')
        amount = request.data.get('amount')

        if not account_id or not amount:
            return Response(
                {"error": "Se requieren account_id y amount"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            amount_decimal = Decimal(str(amount))

            if amount_decimal <= 0:
                return Response(
                    {"error": "El monto debe ser mayor a cero"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            client = WompiPayoutsClient()
            result = client.recharge_balance_sandbox(account_id, amount_decimal)

            # Log de auditoría
            AuditLog.objects.create(
                admin_user=request.user,
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details=f"Recarga sandbox Wompi: ${amount_decimal} COP en cuenta {account_id}"
            )

            return Response({
                "success": True,
                "account_id": account_id,
                "amount": str(amount_decimal),
                "message": "Saldo recargado exitosamente",
                "result": result
            })

        except (ValueError, Decimal.InvalidOperation):
            return Response(
                {"error": "Monto inválido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except WompiPayoutsError as exc:
            logger.exception("Error recargando saldo en Wompi Sandbox")
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class WompiPayoutsWebhookView(APIView):
    """
    Webhook endpoint para recibir eventos de Wompi Payouts API.

    POST /api/v1/finances/wompi-payouts/webhook/

    Wompi envía eventos cuando cambia el estado de un payout o transacción.

    Eventos soportados:
    - payout.updated: Cambio de estado en un lote de pago
    - transaction.updated: Cambio de estado en una transacción individual

    Headers esperados:
    - X-Signature: Firma HMAC SHA256 del payload con WOMPI_PAYOUT_EVENTS_SECRET

    Payload de ejemplo:
    {
        "event": "transaction.updated",
        "data": {
            "id": "transaction-uuid",
            "status": "APPROVED",
            "reference": "DEV-COMM-20251231-120000",
            "amount": 5000000,
            "payoutId": "payout-uuid"
        }
    }
    """
    permission_classes = [AllowAny]  # Wompi no puede autenticarse

    def post(self, request):
        # Extraer firma del header
        signature = request.META.get('HTTP_X_SIGNATURE', '')

        if not signature:
            logger.warning("[Wompi Payouts Webhook] Request sin firma X-Signature")
            return Response(
                {"error": "Missing X-Signature header"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Validar firma
        if not WompiPayoutsWebhookService.validate_signature(request.data, signature):
            logger.warning(
                "[Wompi Payouts Webhook] Firma inválida. Posible intento de falsificación."
            )
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Extraer tipo de evento
        event_type = request.data.get('event')

        if not event_type:
            logger.error("[Wompi Payouts Webhook] Payload sin campo 'event'")
            return Response(
                {"error": "Missing event type"},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(
            "[Wompi Payouts Webhook] Recibido evento: %s",
            event_type
        )

        try:
            # Procesar evento
            result = WompiPayoutsWebhookService.process_event(event_type, request.data)

            return Response(
                {
                    "status": "webhook_processed",
                    "event_type": event_type,
                    "result": result
                },
                status=status.HTTP_200_OK
            )

        except Exception as exc:
            logger.exception(
                "[Wompi Payouts Webhook] Error procesando evento %s: %s",
                event_type,
                exc
            )
            # Retornar 200 para que Wompi no reintente
            # (el error ya está loggeado para revisión manual)
            return Response(
                {
                    "status": "error",
                    "message": "Internal error processing webhook",
                    "event_type": event_type
                },
                status=status.HTTP_200_OK
            )


# ========================================
# ANALYTICS DE FINANZAS - SERVICIOS
# ========================================

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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

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
            count=models.Count('id'),
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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

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
            count=models.Count('id'),
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
            count=models.Count('id'),
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
            count=models.Count('id'),
            revenue=Coalesce(Sum('price_at_purchase'), Decimal('0'))
        )

        # 4. Servicios cancelados
        cancelled = base_qs.filter(
            status=Appointment.AppointmentStatus.CANCELLED
        ).aggregate(
            count=models.Count('id'),
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


# ========================================
# ANALYTICS DE FINANZAS - MARKETPLACE
# ========================================

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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

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
            count=models.Count('order_id', distinct=True)
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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
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
            count=models.Count('id')
        )
        orders_by_status = {item['status'].lower(): item['count'] for item in orders_by_status_raw}

        # Métodos de entrega
        delivery_methods_raw = base_qs.values('delivery_option').annotate(
            count=models.Count('id')
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
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

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
            orders=models.Count('order_id', distinct=True)
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

