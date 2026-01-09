"""
Servicio de Créditos - Aplicación FIFO de saldo a favor.

Contiene:
- CreditApplicationResult: Resultado de aplicar créditos
- Funciones apply_credits_to_payment y preview_credits_application
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from finances.models import ClientCredit


logger = logging.getLogger(__name__)


class CreditApplicationResult:
    """Resultado de aplicar créditos a un monto."""
    def __init__(self, amount_remaining, credits_applied, credit_movements):
        self.amount_remaining = amount_remaining
        self.credits_applied = credits_applied
        self.credit_movements = credit_movements  # List of (ClientCredit, Decimal amount_used)

    @property
    def fully_covered(self):
        """Retorna True si los créditos cubrieron todo el monto."""
        return self.amount_remaining <= Decimal('0')


@transaction.atomic
def apply_credits_to_payment(user, total_amount):
    """
    Aplica créditos disponibles del usuario a un monto total.

    Esta función:
    1. Busca créditos disponibles y no expirados del usuario
    2. Los aplica en orden FIFO (primero los más antiguos)
    3. Actualiza el remaining_amount y status de cada crédito usado
    4. Retorna cuánto falta por pagar y los movimientos de crédito

    Args:
        user: Usuario que posee los créditos
        total_amount: Monto total a cubrir con créditos

    Returns:
        CreditApplicationResult con:
            - amount_remaining: Decimal del monto que quedó sin cubrir
            - credits_applied: Decimal del total de créditos usados
            - credit_movements: List[(ClientCredit, Decimal)] movimientos realizados
    """
    if total_amount <= Decimal('0'):
        return CreditApplicationResult(
            amount_remaining=total_amount,
            credits_applied=Decimal('0'),
            credit_movements=[]
        )

    # Buscar créditos válidos (disponibles, no expirados) del usuario
    available_credits = ClientCredit.objects.select_for_update().filter(
        user=user,
        status__in=[
            ClientCredit.CreditStatus.AVAILABLE,
            ClientCredit.CreditStatus.PARTIALLY_USED
        ],
        expires_at__gte=timezone.now().date()
    ).order_by('created_at')  # FIFO: usar los créditos más antiguos primero

    amount_remaining = total_amount
    credit_movements = []

    for credit in available_credits:
        if amount_remaining <= Decimal('0'):
            break

        # Calcular cuánto tomar de este crédito
        amount_from_this_credit = min(amount_remaining, credit.remaining_amount)

        # Actualizar el crédito
        credit.remaining_amount -= amount_from_this_credit

        # Actualizar estado del crédito
        if credit.remaining_amount <= Decimal('0'):
            credit.status = ClientCredit.CreditStatus.USED
        else:
            credit.status = ClientCredit.CreditStatus.PARTIALLY_USED

        credit.save(update_fields=['remaining_amount', 'status', 'updated_at'])

        # Registrar el movimiento
        credit_movements.append((credit, amount_from_this_credit))
        amount_remaining -= amount_from_this_credit

        logger.info(
            "Crédito aplicado: credit_id=%s, user=%s, used=%s, remaining=%s",
            credit.id, user.id, amount_from_this_credit, credit.remaining_amount
        )

    credits_applied = total_amount - amount_remaining

    return CreditApplicationResult(
        amount_remaining=amount_remaining,
        credits_applied=credits_applied,
        credit_movements=credit_movements
    )


def preview_credits_application(user, total_amount):
    """
    Calcula cuántos créditos se aplicarían a un monto SIN modificar la base de datos.
    
    Esta función es SOLO LECTURA - no modifica ningún crédito.
    Usar para mostrar preview antes de confirmar el pago.
    
    Args:
        user: Usuario que posee los créditos
        total_amount: Monto total a evaluar
        
    Returns:
        dict con:
            - available_credits: Total de créditos disponibles
            - credits_to_apply: Cuánto se aplicaría de créditos
            - amount_remaining: Cuánto quedaría por pagar después de créditos
            - fully_covered: Si los créditos cubren todo el monto
    """
    if total_amount <= Decimal('0'):
        return {
            'available_credits': Decimal('0'),
            'credits_to_apply': Decimal('0'),
            'amount_remaining': total_amount,
            'fully_covered': True
        }
    
    # Buscar créditos válidos (disponibles, no expirados) del usuario - SOLO LECTURA
    available_credits = ClientCredit.objects.filter(
        user=user,
        status__in=[
            ClientCredit.CreditStatus.AVAILABLE,
            ClientCredit.CreditStatus.PARTIALLY_USED
        ],
        expires_at__gte=timezone.now().date()
    ).order_by('created_at')  # FIFO: usar los créditos más antiguos primero
    
    total_available = sum(c.remaining_amount for c in available_credits)
    credits_to_apply = min(total_amount, total_available)
    amount_remaining = max(Decimal('0'), total_amount - credits_to_apply)
    
    return {
        'available_credits': total_available,
        'credits_to_apply': credits_to_apply,
        'amount_remaining': amount_remaining,
        'fully_covered': amount_remaining <= Decimal('0')
    }
