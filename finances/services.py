from __future__ import annotations

import logging
import os
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import GlobalSettings, AuditLog
from core.utils import safe_audit_log
from .models import CommissionLedger

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class WompiPayoutError(Exception):
    """Errores al consultar o ejecutar dispersión con Wompi."""


class WompiDisbursementClient:
    """
    Cliente sencillo para consultar saldo y ejecutar payouts en Wompi.
    Depende de las variables de entorno:
        - WOMPI_PAYOUT_PRIVATE_KEY
        - WOMPI_PAYOUT_BASE_URL
        - WOMPI_DEVELOPER_DESTINATION
    """

    REQUEST_TIMEOUT = 10
    _CIRCUIT_CACHE_KEY = "wompi:disbursement:circuit"

    def __init__(self):
        self.private_key = (
            getattr(settings, "WOMPI_PAYOUT_PRIVATE_KEY", None)
            or os.getenv("WOMPI_PAYOUT_PRIVATE_KEY")
        )
        self.base_url = (
            getattr(settings, "WOMPI_PAYOUT_BASE_URL", None)
            or os.getenv("WOMPI_PAYOUT_BASE_URL", "")
        ).rstrip("/")
        self.balance_endpoint = f"{self.base_url}/accounts" if self.base_url else ""
        self.payout_endpoint = f"{self.base_url}/transfers" if self.base_url else ""
        self.destination = (
            getattr(settings, "WOMPI_DEVELOPER_DESTINATION", None)
            or os.getenv("WOMPI_DEVELOPER_DESTINATION", "")
        )

    @classmethod
    def _circuit_allows(cls):
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        open_until = state.get("open_until")
        if open_until and open_until > timezone.now():
            return False
        return True

    @classmethod
    def _record_failure(cls, max_failures=5, cooldown_seconds=60):
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        failures = state.get("failures", 0) + 1
        open_until = state.get("open_until")
        if failures >= max_failures:
            open_until = timezone.now() + timedelta(seconds=cooldown_seconds)
            failures = 0
        cache.set(cls._CIRCUIT_CACHE_KEY, {"failures": failures, "open_until": open_until}, timeout=cooldown_seconds)

    @classmethod
    def _record_success(cls):
        cache.set(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None}, timeout=60)

    def _headers(self):
        if not self.private_key:
            raise WompiPayoutError("Falta WOMPI_PAYOUT_PRIVATE_KEY para intentar la dispersión.")
        return {"Authorization": f"Bearer {self.private_key}"}

    def get_available_balance(self) -> Decimal:
        if not self._circuit_allows():
            logger.warning("Circuito de Wompi (dispersión) abierto; se omite consulta de balance.")
            return Decimal("0")
        if not self.balance_endpoint or not self.private_key:
            logger.warning("Balance Wompi no disponible: configura WOMPI_PAYOUT_BASE_URL y WOMPI_PAYOUT_PRIVATE_KEY.")
            return Decimal("0")
        try:
            response = requests.get(self.balance_endpoint, headers=self._headers(), timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json() or {}
            accounts = data.get("data") or []
            if isinstance(accounts, dict):
                accounts = accounts.get("accounts") or []
            if not accounts:
                return Decimal("0.00")
            account = accounts[0]
            cents = account.get("balanceInCents") or account.get("balance_in_cents") or 0
            amount = _to_decimal(cents) / Decimal("100")
            self._record_success()
            return amount.quantize(Decimal("0.01"))
        except requests.Timeout as exc:
            self._record_failure()
            logger.exception("Timeout consultando balance en Wompi: %s", exc)
            raise WompiPayoutError("Timeout consultando balance en Wompi") from exc
        except (requests.RequestException, ValueError) as exc:
            self._record_failure()
            logger.exception("No se pudo obtener el balance en Wompi: %s", exc)
            return Decimal("0")

    def create_payout(self, amount: Decimal) -> str:
        if not self.payout_endpoint or not self.destination:
            raise WompiPayoutError("Configura WOMPI_PAYOUT_BASE_URL y WOMPI_DEVELOPER_DESTINATION para dispersar fondos.")
        if amount is None or _to_decimal(amount) <= Decimal("0"):
            raise WompiPayoutError("El monto a dispersar debe ser mayor a cero.")
        payload = {
            "amount_in_cents": int(amount * Decimal("100")),
            "currency": getattr(settings, "WOMPI_CURRENCY", "COP"),
            "destination_id": self.destination,
            "purpose": "developer_commission",
        }
        try:
            response = requests.post(self.payout_endpoint, json=payload, headers=self._headers(), timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json() or {}
            self._record_success()
            return data.get("data", {}).get("id") or data.get("id") or ""
        except requests.Timeout as exc:
            self._record_failure()
            raise WompiPayoutError("Timeout al crear la dispersión en Wompi") from exc
        except requests.RequestException as exc:
            self._record_failure()
            raise WompiPayoutError(f"No se pudo crear el payout: {exc}") from exc


class DeveloperCommissionService:
    """
    Orquesta el registro de comisiones, cálculo de deuda y pagos al desarrollador.
    """

    @classmethod
    @transaction.atomic
    def register_commission(cls, payment):
        if payment is None or payment.amount in (None, Decimal("0")):
            return None

        if CommissionLedger.objects.filter(source_payment=payment).exists():
            return None

        settings_obj = GlobalSettings.load()
        percentage = settings_obj.developer_commission_percentage
        if not percentage or percentage <= 0:
            return None

        amount = (
            _to_decimal(payment.amount)
            * _to_decimal(percentage)
            / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amount <= 0:
            return None

        return CommissionLedger.objects.create(
            amount=amount,
            source_payment=payment,
            status=CommissionLedger.Status.PENDING,
        )

    @staticmethod
    def get_developer_debt(include_failed: bool = True) -> Decimal:
        statuses = [CommissionLedger.Status.PENDING]
        if include_failed:
            statuses.append(CommissionLedger.Status.FAILED_NSF)
        aggregate = CommissionLedger.objects.filter(
            status__in=statuses
        ).aggregate(total=Coalesce(Sum(F("amount") - F("paid_amount")), Decimal("0")))
        total = aggregate["total"] or Decimal("0")
        return total.quantize(Decimal("0.01"))

    @classmethod
    def handle_successful_payment(cls, payment):
        ledger = cls.register_commission(payment)
        if not ledger:
            return None
        return cls.evaluate_payout()

    @classmethod
    def evaluate_payout(cls):
        settings_obj = GlobalSettings.load()
        debt = cls.get_developer_debt()
        if debt <= Decimal("0"):
            cls._exit_default(settings_obj)
            return {"status": "no_debt"}

        threshold = settings_obj.developer_payout_threshold
        if not settings_obj.developer_in_default and debt < threshold:
            return {"status": "below_threshold", "debt": str(debt)}

        return cls._attempt_payout(settings_obj, debt)

    @classmethod
    def _attempt_payout(cls, settings_obj, current_debt: Decimal):
        client = WompiDisbursementClient()
        try:
            balance = client.get_available_balance()
        except WompiPayoutError as exc:
            logger.error("No se pudo consultar saldo Wompi: %s", exc)
            cls._enter_default(settings_obj)
            cls._mark_failed_nsf()
            return {"status": "balance_unavailable", "detail": str(exc)}

        amount_to_pay = min(current_debt, balance)
        if amount_to_pay <= Decimal("0"):
            cls._enter_default(settings_obj)
            cls._mark_failed_nsf()
            return {"status": "insufficient_funds", "debt": str(current_debt), "balance": str(balance)}

        try:
            wompi_transfer_id = client.create_payout(amount_to_pay)
        except WompiPayoutError as exc:
            logger.error("Payout al desarrollador falló: %s", exc)
            cls._enter_default(settings_obj)
            cls._mark_failed_nsf()
            return {"status": "payout_failed", "detail": str(exc)}

        cls._apply_payout_to_ledger(amount_to_pay, wompi_transfer_id)
        remaining_debt = cls.get_developer_debt()
        if remaining_debt <= Decimal("0"):
            cls._exit_default(settings_obj)
        else:
            cls._enter_default(settings_obj)
        return {"status": "paid", "amount": str(amount_to_pay), "remaining_debt": str(remaining_debt)}

    @classmethod
    @transaction.atomic
    def _apply_payout_to_ledger(cls, amount_to_pay: Decimal, transfer_id: str, performed_by=None):
        remaining = amount_to_pay
        entries = (
            CommissionLedger.objects.select_for_update()
            .filter(status__in=[CommissionLedger.Status.PENDING, CommissionLedger.Status.FAILED_NSF])
            .order_by("created_at")
        )
        now = timezone.now()
        paid_entries = []
        for entry in entries:
            if remaining <= Decimal("0"):
                break
            due = entry.pending_amount
            if due <= Decimal("0"):
                continue
            chunk = min(due, remaining)
            previous_status = entry.status
            entry.paid_amount = (entry.paid_amount or Decimal("0")) + chunk
            entry.wompi_transfer_id = transfer_id
            if entry.paid_amount >= entry.amount:
                entry.status = CommissionLedger.Status.PAID
                entry.paid_at = now
            entry.save(
                update_fields=[
                    "paid_amount",
                    "status",
                    "wompi_transfer_id",
                    "paid_at",
                    "updated_at",
                ]
            )
            paid_entries.append(entry)
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                admin_user=performed_by,
                details={
                    "action": "commission_payout_applied",
                    "ledger_id": str(entry.id),
                    "payment_id": str(entry.source_payment_id),
                    "amount_paid": str(chunk),
                    "previous_status": previous_status,
                    "new_status": entry.status,
                    "wompi_transfer_id": transfer_id,
                    "total_paid": str(entry.paid_amount),
                    "total_amount": str(entry.amount),
                },
            )
            remaining -= chunk
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=performed_by,
            details={
                "action": "developer_payout_completed",
                "total_amount": str(amount_to_pay),
                "wompi_transfer_id": transfer_id,
                "entries_paid": len(paid_entries),
                "timestamp": now.isoformat(),
            },
        )

    @staticmethod
    def _enter_default(settings_obj):
        if not settings_obj.developer_in_default:
            settings_obj.developer_in_default = True
            settings_obj.developer_default_since = timezone.now()
            settings_obj.save(update_fields=["developer_in_default", "developer_default_since", "updated_at"])
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details={
                    "action": "developer_default_entered",
                    "timestamp": timezone.now().isoformat(),
                },
            )

    @staticmethod
    def _exit_default(settings_obj):
        if settings_obj.developer_in_default:
            settings_obj.developer_in_default = False
            settings_obj.developer_default_since = None
            settings_obj.save(update_fields=["developer_in_default", "developer_default_since", "updated_at"])
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details={
                    "action": "developer_default_exited",
                    "timestamp": timezone.now().isoformat(),
                },
            )

    @classmethod
    @transaction.atomic
    def _mark_failed_nsf(cls):
        CommissionLedger.objects.select_for_update().filter(
            status=CommissionLedger.Status.PENDING
        ).update(
            status=CommissionLedger.Status.FAILED_NSF,
            updated_at=timezone.now(),
        )
