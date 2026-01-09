from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Dict

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class WompiPayoutsError(Exception):
    """Errores relacionados con Wompi Payouts API."""


class WompiPayoutsBase:
    """Config y helpers base para el cliente de payouts."""

    def __init__(self):
        self.api_key = getattr(settings, "WOMPI_PAYOUT_PRIVATE_KEY", "")
        self.user_id = getattr(settings, "WOMPI_PAYOUT_USER_ID", "")
        self.base_url = (getattr(settings, "WOMPI_PAYOUT_BASE_URL", "") or "").rstrip("/")
        self.mode = getattr(settings, "WOMPI_PAYOUT_MODE", "sandbox")
        self.currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        if not self.api_key or not self.user_id or not self.base_url:
            logger.warning(
                "Wompi Payouts no configurado correctamente. "
                "Verifica WOMPI_PAYOUT_PRIVATE_KEY, WOMPI_PAYOUT_USER_ID y WOMPI_PAYOUT_BASE_URL"
            )

    def _headers(self) -> Dict[str, str]:
        if not self.api_key or not self.user_id:
            raise WompiPayoutsError(
                "Configuración incompleta. Se requieren WOMPI_PAYOUT_PRIVATE_KEY y WOMPI_PAYOUT_USER_ID"
            )

        return {
            "x-api-key": self.api_key,
            "user-principal-id": self.user_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class WompiPayoutsCircuitMixin:
    """Circuit breaker simple para proteger al cliente."""

    _CIRCUIT_CACHE_KEY = "wompi:payouts:circuit"

    @classmethod
    def _circuit_allows(cls) -> bool:
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        open_until = state.get("open_until")
        if open_until and open_until > timezone.now():
            logger.warning("Circuit breaker abierto hasta %s. Rechazando request.", open_until.isoformat())
            return False
        return True

    @classmethod
    def _record_failure(cls, max_failures: int = 5, cooldown_seconds: int = 120):
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        failures = state.get("failures", 0) + 1
        open_until = state.get("open_until")

        if failures >= max_failures:
            open_until = timezone.now() + timedelta(seconds=cooldown_seconds)
            logger.error(
                "Circuit breaker ABIERTO por %d fallas consecutivas. Bloqueando requests hasta %s",
                failures,
                open_until.isoformat(),
            )
            failures = 0

        cache.set(
            cls._CIRCUIT_CACHE_KEY,
            {"failures": failures, "open_until": open_until},
            timeout=cooldown_seconds + 60,
        )

    @classmethod
    def _record_success(cls):
        cache.set(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None}, timeout=300)


class WompiPayoutsHttpMixin(WompiPayoutsCircuitMixin):
    """HTTP layer con reintentos y backoff."""

    def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        if not self._circuit_allows():
            raise WompiPayoutsError("Circuit breaker abierto. Servicio temporalmente no disponible.")

        url = f"{self.base_url}{endpoint}"
        last_exc = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.debug("[Wompi Payouts] %s %s (intento %d/%d)", method.upper(), endpoint, attempt, self.MAX_RETRIES)

                response = requests.request(
                    method=method,
                    url=url,
                    timeout=self.REQUEST_TIMEOUT,
                    headers=self._headers(),
                    **kwargs,
                )

                logger.debug("[Wompi Payouts] Response %d: %s", response.status_code, response.text[:500] if response.text else "empty")

                response.raise_for_status()

                self._record_success()
                return response

            except (requests.Timeout, requests.RequestException) as exc:
                last_exc = exc
                self._record_failure()

                if attempt >= self.MAX_RETRIES:
                    logger.error(
                        "[Wompi Payouts] Falló después de %d intentos: %s %s - %s",
                        self.MAX_RETRIES,
                        method.upper(),
                        endpoint,
                        str(exc),
                    )
                    raise WompiPayoutsError(f"Request falló: {exc}") from exc

                sleep_for = self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                logger.warning(
                    "[Wompi Payouts] Error en intento %d/%d: %s. Reintentando en %.1fs",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                    sleep_for,
                )
                time.sleep(sleep_for)

        raise WompiPayoutsError(f"Request falló después de {self.MAX_RETRIES} intentos: {last_exc}")
