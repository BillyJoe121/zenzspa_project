import logging
from decimal import Decimal

from django.utils import timezone

from ..payouts import WompiPayoutsClient, WompiPayoutsError

# Mantener alias legacy para compatibilidad
WompiPayoutError = WompiPayoutsError

logger = logging.getLogger(__name__)


class WompiDisbursementClient:
    """
    Cliente wrapper para mantener compatibilidad con código existente.

    Delega todas las operaciones al nuevo WompiPayoutsClient que implementa
    correctamente la API de Wompi Payouts.
    """

    def __init__(self):
        self._client = WompiPayoutsClient()

    def get_available_balance(self, account_id: str | None = None) -> Decimal:
        try:
            return self._client.get_available_balance(account_id=account_id)
        except WompiPayoutsError as exc:
            raise WompiPayoutError(str(exc)) from exc

    def create_payout(self, amount: Decimal, reference: str | None = None) -> str:
        if not reference:
            reference = f"DEV-COMM-{timezone.now().strftime('%Y%m%d-%H%M%S')}"

        try:
            payout_id, payout_data = self._client.create_payout(
                amount=amount,
                reference=reference,
                beneficiary_data=None,
                account_id=None,
            )
            logger.info(
                "Payout creado para desarrollador: ID=%s, Monto=$%s, Estado=%s",
                payout_id,
                amount,
                payout_data.get("status", "unknown"),
            )
            return payout_id
        except WompiPayoutsError as exc:
            raise WompiPayoutError(str(exc)) from exc
