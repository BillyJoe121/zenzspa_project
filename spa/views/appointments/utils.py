"""
Utilidades compartidas para las vistas de appointments.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog

logger = logging.getLogger(__name__)


def append_cancellation_strike(*, user, appointment, strike_type, credit=None, amount=Decimal('0')):
    """
    Agrega un registro al historial de cancelaciones del usuario.

    Args:
        user: Usuario al que se le agrega el strike
        appointment: Cita relacionada con el strike
        strike_type: Tipo de strike (CANCEL, RESCHEDULE, etc.)
        credit: Crédito asociado (opcional)
        amount: Monto del crédito (opcional)

    Returns:
        list: Historial actualizado de strikes
    """
    if not user:
        return list()
    history = list(user.cancellation_streak or [])
    entry = {
        "appointment_id": str(getattr(appointment, "id", "")),
        "credit_id": str(getattr(credit, "id", "")) if credit else None,
        "amount": float(amount or Decimal('0')),
        "type": strike_type,
        "timestamp": timezone.now().isoformat(),
    }
    history.append(entry)
    user.cancellation_streak = history
    user.save(update_fields=['cancellation_streak', 'updated_at'])
    return history


