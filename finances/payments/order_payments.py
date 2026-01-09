"""
Pagos de Órdenes y Paquetes.

Contiene:
- create_package_payment: Crea pago para compra de paquete
- create_order_payment: Crea pago para orden de marketplace con soporte de créditos
"""
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction

from finances.gateway import WompiPaymentClient, build_integrity_signature
from finances.models import Payment, PaymentCreditUsage
from finances.services import DeveloperCommissionService
from finances.payments.credits import apply_credits_to_payment


logger = logging.getLogger(__name__)


@transaction.atomic
def create_package_payment(user, package):
    """
    Crea un registro de pago para la compra de un paquete.
    """
    reference = f"PACKAGE-{package.id}-{uuid.uuid4().hex[:8]}"
    
    payment = Payment.objects.create(
        user=user,
        amount=package.price,
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.PACKAGE,
        transaction_id=reference
    )
    return payment


@transaction.atomic
def create_order_payment(user, order, use_credits=False):
    """
    Crea o actualiza un registro de pago para una orden de marketplace
    y prepara los datos para Wompi con una referencia única.

    Si use_credits=True, aplica créditos disponibles del usuario al monto total.
    Puede resultar en:
    - Pago totalmente cubierto con créditos (sin ir a Wompi)
    - Pago parcial con créditos + remanente para Wompi
    - Pago normal si no hay créditos disponibles

    Args:
        user: Usuario que realiza el pago
        order: Orden de marketplace
        use_credits: Si debe aplicar créditos disponibles del usuario

    Returns:
        tuple: (payment, payment_payload)
            - payment: Objeto Payment creado (o None si totalmente cubierto con crédito)
            - payment_payload: Dict con datos para Wompi (o dict con status si pagado con crédito)
    """
    total_amount = order.total_amount
    credits_applied = Decimal('0')
    credit_movements = []

    # Aplicar créditos si el usuario lo solicita
    if use_credits:
        credit_result = apply_credits_to_payment(user, total_amount)
        credits_applied = credit_result.credits_applied
        credit_movements = credit_result.credit_movements
        amount_to_pay = credit_result.amount_remaining

        logger.info(
            "Créditos aplicados a orden: order_id=%s, user=%s, credits_used=%s, remaining=%s",
            order.id, user.id, credits_applied, amount_to_pay
        )
    else:
        amount_to_pay = total_amount

    # Si los créditos cubrieron TODO el monto
    if use_credits and credits_applied > 0 and amount_to_pay <= Decimal('0'):
        # Crear pago completamente cubierto con crédito
        reference = f"ORDER-CREDIT-{order.id}-{uuid.uuid4().hex[:8]}"

        payment = Payment.objects.create(
            user=user,
            amount=credits_applied,
            status=Payment.PaymentStatus.PAID_WITH_CREDIT,
            payment_type=Payment.PaymentType.ORDER,
            transaction_id=reference,
            order=order,
            used_credit=credit_movements[0][0] if credit_movements else None
        )

        # Crear registros de uso de crédito para trazabilidad
        PaymentCreditUsage.objects.bulk_create([
            PaymentCreditUsage(
                payment=payment,
                credit=credit,
                amount=used_amount
            )
            for credit, used_amount in credit_movements
        ])

        # La orden se confirma automáticamente
        from marketplace.services import OrderService
        OrderService.confirm_payment(order)

        # Registrar comisión del desarrollador
        DeveloperCommissionService.handle_successful_payment(payment)

        # Retornar payload especial indicando que se pagó con crédito
        return payment, {
            'status': 'paid_with_credit',
            'paymentId': str(payment.id),
            'credits_used': str(credits_applied),
            'amount_paid': '0',
            'order_status': order.status
        }

    # Si hay créditos parciales o no hay créditos, crear pago para Wompi
    # Generar SIEMPRE una nueva referencia para permitir reintentos
    reference = f"ORDER-{order.id}-{uuid.uuid4().hex[:8]}"

    # Si se aplicaron créditos parcialmente, crear primero el pago con crédito
    if use_credits and credits_applied > 0:
        credit_payment = Payment.objects.create(
            user=user,
            amount=credits_applied,
            status=Payment.PaymentStatus.PAID_WITH_CREDIT,
            payment_type=Payment.PaymentType.ORDER,
            transaction_id=f"ORDER-CREDIT-{order.id}-{uuid.uuid4().hex[:8]}",
            order=order,
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
            "Pago parcial con crédito creado: order_id=%s, payment_id=%s, amount=%s",
            order.id, credit_payment.id, credits_applied
        )

    # Buscar si ya existe un pago pendiente para esta orden
    payment = Payment.objects.filter(
        order=order,
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.ORDER
    ).first()

    if payment:
        # Actualizar pago existente con nueva referencia y monto ajustado
        payment.transaction_id = reference
        payment.amount = amount_to_pay
        payment.user = user
        payment.save(update_fields=['transaction_id', 'amount', 'user', 'updated_at'])
    else:
        # Crear nuevo pago pendiente por el remanente
        payment = Payment.objects.create(
            user=user,
            amount=amount_to_pay,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ORDER,
            transaction_id=reference,
            order=order,
        )

    order.wompi_transaction_id = reference
    order.save(update_fields=['wompi_transaction_id', 'updated_at'])

    amount_in_cents = int(amount_to_pay * 100)

    # Obtener acceptance token
    try:
        acceptance_token = WompiPaymentClient.resolve_acceptance_token()
        if not acceptance_token:
             raise ValueError("No se pudo obtener el token de aceptación de Wompi.")
    except requests.RequestException as e:
        raise ValueError(f"Error al comunicarse con Wompi: {str(e)}")

    signature = build_integrity_signature(
        reference=reference,
        amount_in_cents=amount_in_cents,
        currency=getattr(settings, "WOMPI_CURRENCY", "COP"),
    )

    payment_payload = {
        'publicKey': settings.WOMPI_PUBLIC_KEY,
        'currency': getattr(settings, "WOMPI_CURRENCY", "COP"),
        'amountInCents': amount_in_cents,
        'reference': reference,
        'signatureIntegrity': signature,
        'redirectUrl': settings.WOMPI_REDIRECT_URL,
        'acceptanceToken': acceptance_token,
        'paymentId': str(payment.id),
    }

    # Si se aplicaron créditos parciales, agregar info al payload
    if use_credits and credits_applied > 0:
        payment_payload['credits_used'] = str(credits_applied)
        payment_payload['original_amount'] = str(total_amount)
        payment_payload['status'] = 'partial_credit'

    return payment, payment_payload
