"""
Cliente para Wompi Payouts API (Pagos a Terceros).

Divide responsabilidades en módulos (base, cuentas y transacciones) y reexporta
WompiPayoutsClient/WompiPayoutsError para compatibilidad.
"""
from __future__ import annotations

from .accounts import WompiPayoutsAccountsMixin
from .base import WompiPayoutsBase, WompiPayoutsError
from .transactions import WompiPayoutsTransactionsMixin


class WompiPayoutsClient(
    WompiPayoutsTransactionsMixin,
    WompiPayoutsAccountsMixin,
    WompiPayoutsBase,
):
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 1.0

    class BatchStatus:
        PENDING_APPROVAL = "PENDING_APPROVAL"
        PENDING = "PENDING"
        NOT_APPROVED = "NOT_APPROVED"
        REJECTED = "REJECTED"
        PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
        TOTAL_PAYMENT = "TOTAL_PAYMENT"

    class TransactionStatus:
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        CANCELLED = "CANCELLED"
        FAILED = "FAILED"

    def __init__(self):
        super().__init__()


__all__ = ["WompiPayoutsClient", "WompiPayoutsError"]
