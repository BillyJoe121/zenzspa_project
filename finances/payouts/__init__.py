"""
Cliente para Wompi Payouts API (Pagos a Terceros).

Divide responsabilidades en módulos (base, cuentas y transacciones) y reexporta
WompiPayoutsClient/WompiPayoutsError para compatibilidad.
"""
from __future__ import annotations

from .client import WompiPayoutsClient, WompiPayoutsError


__all__ = ["WompiPayoutsClient", "WompiPayoutsError"]
