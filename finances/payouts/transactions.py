import hashlib
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

from .base import WompiPayoutsError, WompiPayoutsHttpMixin


class WompiPayoutsTransactionsMixin(WompiPayoutsHttpMixin):
    """Operaciones de creación y consulta de payouts."""

    def create_payout(
        self,
        amount: Decimal,
        reference: str,
        beneficiary_data: Optional[Dict[str, str]] = None,
        account_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if amount <= Decimal("0"):
            raise WompiPayoutsError("El monto debe ser mayor a cero")

        if not account_id:
            accounts = self.get_accounts()
            if not accounts:
                raise WompiPayoutsError("No hay cuentas disponibles para dispersión")
            account_id = accounts[0].get("id")

        if not beneficiary_data:
            beneficiary_data = {
                "legalIdType": getattr(settings, "WOMPI_DEVELOPER_LEGAL_ID_TYPE", "CC"),
                "legalId": getattr(settings, "WOMPI_DEVELOPER_LEGAL_ID", ""),
                "bankId": getattr(settings, "WOMPI_DEVELOPER_BANK_ID", "1007"),
                "accountType": getattr(settings, "WOMPI_DEVELOPER_ACCOUNT_TYPE", "AHORROS"),
                "accountNumber": getattr(settings, "WOMPI_DEVELOPER_ACCOUNT_NUMBER", ""),
                "name": getattr(settings, "WOMPI_DEVELOPER_NAME", ""),
                "email": getattr(settings, "WOMPI_DEVELOPER_EMAIL", ""),
            }

        self._validate_beneficiary_data(beneficiary_data)

        if not idempotency_key:
            idempotency_key = self._generate_idempotency_key(reference, amount)

        amount_in_cents = int(amount * Decimal("100"))

        payload = {
            "accountId": account_id,
            "transactions": [
                {
                    "legalIdType": beneficiary_data["legalIdType"],
                    "legalId": beneficiary_data["legalId"],
                    "bankId": beneficiary_data["bankId"],
                    "accountType": beneficiary_data["accountType"],
                    "accountNumber": beneficiary_data["accountNumber"],
                    "name": beneficiary_data["name"],
                    "email": beneficiary_data["email"],
                    "amount": amount_in_cents,
                    "reference": reference,
                    "paymentType": getattr(settings, "WOMPI_PAYOUT_PAYMENT_TYPE", "OTHER"),
                }
            ],
            "idempotencyKey": idempotency_key,
        }

        try:
            response = self._request_with_retry("POST", "/payouts", json=payload)
            data = response.json()
            payout_data = data.get("data", {})
            payout_id = payout_data.get("id")

            if not payout_id:
                raise WompiPayoutsError("La respuesta de Wompi no incluyó un ID de lote")

            return payout_id, payout_data

        except Exception as exc:
            raise WompiPayoutsError(f"No se pudo crear el payout: {exc}") from exc

    def get_payout(self, payout_id: str) -> Dict[str, Any]:
        try:
            response = self._request_with_retry("GET", f"/payouts/{payout_id}")
            data = response.json()
            return data.get("data", {})
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudo consultar el payout: {exc}") from exc

    def get_payout_transactions(self, payout_id: str) -> List[Dict[str, Any]]:
        try:
            response = self._request_with_retry("GET", f"/payouts/{payout_id}/transactions")
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudieron consultar las transacciones: {exc}") from exc

    def get_transaction_by_reference(self, reference: str) -> Optional[Dict[str, Any]]:
        try:
            response = self._request_with_retry("GET", f"/transactions/{reference}")
            data = response.json()
            transactions = data.get("data", [])
            if transactions:
                return transactions[0]
            return None

        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudo consultar la transacción: {exc}") from exc

    def recharge_balance_sandbox(self, account_id: str, amount: Decimal) -> Dict[str, Any]:
        if self.mode != "sandbox":
            raise WompiPayoutsError("La recarga de saldo solo está disponible en modo sandbox")

        amount_in_cents = int(amount * Decimal("100"))
        payload = {"accountId": account_id, "amount": amount_in_cents}

        try:
            response = self._request_with_retry("POST", "/accounts/balance-recharge", json=payload)
            return response.json()
        except Exception as exc:
            raise WompiPayoutsError(f"No se pudo recargar el saldo: {exc}") from exc

    @staticmethod
    def _validate_beneficiary_data(data: Dict[str, str]):
        required_fields = [
            "legalIdType",
            "legalId",
            "bankId",
            "accountType",
            "accountNumber",
            "name",
            "email",
        ]

        for field in required_fields:
            if not data.get(field):
                raise WompiPayoutsError(f"Campo requerido faltante: {field}")

        if data["accountType"] not in ["AHORROS", "CORRIENTE"]:
            raise WompiPayoutsError(f"accountType inválido: {data['accountType']}. Debe ser AHORROS o CORRIENTE")

        account_number = data["accountNumber"]
        if not account_number.isdigit():
            raise WompiPayoutsError("accountNumber debe contener solo números")

        if not (6 <= len(account_number) <= 20):
            raise WompiPayoutsError("accountNumber debe tener entre 6 y 20 dígitos")

        if account_number == "0" * len(account_number):
            raise WompiPayoutsError("accountNumber no puede ser todo ceros")

    @staticmethod
    def _generate_idempotency_key(reference: str, amount: Decimal) -> str:
        today = timezone.now().date().isoformat()
        raw = f"{reference}:{amount}:{today}"
        hash_value = hashlib.sha256(raw.encode()).hexdigest()[:32]
        short_uuid = str(uuid.uuid4())[:8]
        return f"IDMP-{hash_value}-{short_uuid}"
