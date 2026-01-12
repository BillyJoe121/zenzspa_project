from decimal import Decimal
from typing import Any, Dict, List, Optional

from .base import WompiPayoutsError, WompiPayoutsHttpMixin


class WompiPayoutsAccountsMixin(WompiPayoutsHttpMixin):
    """Operaciones de cuentas y bancos."""

    def get_accounts(self) -> List[Dict[str, Any]]:
        try:
            response = self._request_with_retry("GET", "/accounts")
            data = response.json()
            accounts = data.get("data", [])

            if isinstance(accounts, dict):
                accounts = accounts.get("accounts", [])

            return accounts
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudieron obtener las cuentas: {exc}") from exc

    def get_available_balance(self, account_id: Optional[str] = None) -> Decimal:
        accounts = self.get_accounts()
        if not accounts:
            raise WompiPayoutsError("No hay cuentas disponibles")

        target_account = None
        if account_id:
            target_account = next((acc for acc in accounts if acc.get("id") == account_id), None)
            if not target_account:
                raise WompiPayoutsError(f"Cuenta {account_id} no encontrada")
        else:
            target_account = accounts[0]

        balance_cents = target_account.get("balanceInCents") or target_account.get("balance_in_cents") or 0
        balance = Decimal(balance_cents) / Decimal("100")
        return balance.quantize(Decimal("0.01"))

    def get_banks(self) -> List[Dict[str, Any]]:
        try:
            response = self._request_with_retry("GET", "/banks")
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudieron obtener los bancos: {exc}") from exc
