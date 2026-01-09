"""
Gateway Base - WompiGateway y utilidades.

Contiene:
- Métricas Prometheus
- WompiGateway: Cliente para consultar transacciones
- build_integrity_signature: Generador de firma SHA256
"""
import logging
import time
from datetime import timedelta
import hashlib
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.infra.metrics import get_counter, get_histogram


logger = logging.getLogger(__name__)

# Métricas Prometheus
gateway_latency = get_histogram(
    "payment_gateway_latency_seconds",
    "Latencia de llamadas a Wompi",
    ["method", "endpoint", "status"],
)
gateway_failures = get_counter(
    "payment_failures_total",
    "Errores al llamar a Wompi",
    ["reason", "endpoint"],
)


class WompiGateway:
    """
    Cliente liviano para consultar transacciones en Wompi (charge-side).
    Centraliza timeouts, headers y un circuito simple para evitar cascadas.
    """

    REQUEST_TIMEOUT = 10
    _CIRCUIT_CACHE_KEY = "wompi:transactions:circuit"

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
        headers = {}
        if self.private_key:
            headers["Authorization"] = f"Bearer {self.private_key}"
        return headers

    def _request_with_retry(self, method, url, *, json=None, headers=None, timeout=None, attempts=3):
        """
        Ejecuta una petición con reintentos y backoff exponencial corto.
        Usar solo en llamados idempotentes o con referencia fija.
        """
        last_exc = None
        parsed = urlparse(url)
        endpoint = parsed.path
        for attempt in range(1, attempts + 1):
            start = time.perf_counter()
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=headers or {},
                    timeout=timeout or self.REQUEST_TIMEOUT,
                )
                duration = time.perf_counter() - start
                gateway_latency.labels(method, endpoint, resp.status_code).observe(duration)
                return resp
            except requests.Timeout as exc:
                last_exc = exc
                logger.warning("Timeout Wompi %s %s (intento %d/%d)", method, url, attempt, attempts)
                gateway_failures.labels(reason="timeout", endpoint=endpoint).inc()
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Error Wompi %s %s (intento %d/%d): %s", method, url, attempt, attempts, exc)
                gateway_failures.labels(reason="http_error", endpoint=endpoint).inc()

            if attempt < attempts:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        if last_exc:
            gateway_failures.labels(reason="max_retries", endpoint=endpoint).inc()
            raise last_exc
        return None

    def fetch_transaction(self, reference):
        """
        Devuelve el payload de la transacción o None si no hay base URL/reference.
        Lanza requests.HTTPError en caso de status >=400 (comportamiento previo).
        """
        if not self._circuit_allows():
            logger.warning("Circuito de Wompi (transactions) abierto; se omite fetch de %s.", reference)
            return None
        if not self.base_url or not reference:
            return None
        url = f"{self.base_url.rstrip('/')}/transactions/{reference}"
        try:
            response = self._request_with_retry(
                "GET",
                url,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
                attempts=3,
            )
            if response.status_code >= 400:
                self._record_failure()
                response.raise_for_status()
            self._record_success()
            return response.json()
        except requests.Timeout:
            self._record_failure()
            logger.error("Timeout consultando transacción Wompi %s", reference)
            return None
        except requests.RequestException as exc:
            self._record_failure()
            logger.exception("Error consultando transacción Wompi %s: %s", reference, exc)
            return None


def build_integrity_signature(
    reference: str,
    amount_in_cents: int,
    currency: str,
    expiration_time: str | None = None
) -> str | None:
    """
    Genera la firma de integridad para Wompi con soporte para expiration_time.

    SHA256("<reference><amount_in_cents><currency>[<expiration_time>]<INTEGRITY_KEY>")

    Args:
        reference: Referencia única del pago
        amount_in_cents: Monto en centavos
        currency: Moneda (ej: "COP")
        expiration_time: Fecha/hora de expiración en formato ISO8601 UTC (opcional)
                        Ej: "2023-06-09T20:28:50.000Z"

    Returns:
        str: Hash SHA256 hexadecimal o None si falta WOMPI_INTEGRITY_KEY

    Example:
        # Sin expiration_time
        build_integrity_signature("REF-123", 2490000, "COP")
        # Concatena: "REF-1232490000COPtest_integrity_..."

        # Con expiration_time
        build_integrity_signature("REF-123", 2490000, "COP", "2023-06-09T20:28:50.000Z")
        # Concatena: "REF-1232490000COP2023-06-09T20:28:50.000Ztest_integrity_..."
    """
    integrity_key = getattr(settings, "WOMPI_INTEGRITY_KEY", None)
    if not integrity_key:
        logger.warning("WOMPI_INTEGRITY_KEY no configurada, no se puede generar firma")
        return None

    # Concatenar según documentación oficial de Wompi
    if expiration_time:
        concatenated = f"{reference}{amount_in_cents}{currency}{expiration_time}{integrity_key}"
    else:
        concatenated = f"{reference}{amount_in_cents}{currency}{integrity_key}"

    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
