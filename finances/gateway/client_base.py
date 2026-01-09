"""
Cliente Base de Wompi Payment - Funcionalidad core.

Contiene:
- WompiPaymentClientBase: Cliente base con circuit breaker, retry y create_transaction
"""
import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)


class WompiPaymentClientBase:
    """
    Cliente base para crear transacciones en Wompi (cobros).
    Maneja circuit breaker simple y timeouts consistentes.
    """

    REQUEST_TIMEOUT = 15
    _CIRCUIT_CACHE_KEY = "wompi:payments:circuit"

    def __init__(self, base_url: str | None = None, private_key: str | None = None):
        self.base_url = base_url or getattr(settings, "WOMPI_BASE_URL", "")
        self.private_key = private_key or getattr(settings, "WOMPI_PRIVATE_KEY", "")

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
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.private_key}",
            "Content-Type": "application/json",
        }

    def _request_with_retry(self, method, url, *, json=None, headers=None, timeout=None, attempts=2):
        """
        Reintentos con backoff corto solo para operaciones con referencia fija.
        Evita duplicados inadvertidos: el payload debe tener referencia única.
        """
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return requests.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=headers or {},
                    timeout=timeout or self.REQUEST_TIMEOUT,
                )
            except requests.Timeout as exc:
                last_exc = exc
                logger.warning("Timeout Wompi %s %s (intento %d/%d)", method, url, attempt, attempts)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Error Wompi %s %s (intento %d/%d): %s", method, url, attempt, attempts, exc)

            if attempt < attempts:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        if last_exc:
            raise last_exc
        return None

    def create_transaction(self, payload: dict):
        """Crea una transacción en Wompi."""
        if not self._circuit_allows():
            raise requests.RequestException("Circuito Wompi abierto")
        if not self.base_url:
            raise requests.RequestException("WOMPI_BASE_URL no configurada")
        url = f"{self.base_url.rstrip('/')}/transactions"
        try:
            response = self._request_with_retry(
                "POST",
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
                attempts=2,
            )
            data = response.json()
            if response.status_code >= 400:
                self._record_failure()
            else:
                self._record_success()
            return data, response.status_code
        except requests.Timeout as exc:
            self._record_failure()
            raise
        except requests.RequestException:
            self._record_failure()
            raise
        except ValueError as exc:
            self._record_failure()
            raise requests.RequestException(f"Respuesta inválida de Wompi: {exc}") from exc

    @classmethod
    def resolve_acceptance_token(cls, base_url: str | None = None, public_key: str | None = None):
        """Resuelve el token de aceptación de Wompi (cached ~55 min)."""
        configured = getattr(settings, "WOMPI_ACCEPTANCE_TOKEN", None)
        if configured:
            return configured
        cache_key = "wompi:acceptance_token"
        cached = cache.get(cache_key)
        if cached:
            return cached
        base = base_url or getattr(settings, "WOMPI_BASE_URL", "")
        pub_key = public_key or getattr(settings, "WOMPI_PUBLIC_KEY", "")
        if not base or not pub_key:
            return None
        url = f"{base.rstrip('/')}/merchants/{pub_key}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            body = response.json()
            token = body.get("data", {}).get("presigned_acceptance", {}).get("acceptance_token")
            if token:
                cache.set(cache_key, token, timeout=55 * 60)  # ~55 minutos
            return token
        except requests.RequestException:
            logger.exception("No se pudo obtener el acceptance_token desde Wompi.")
            return None
