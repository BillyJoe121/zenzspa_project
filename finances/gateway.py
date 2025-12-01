import logging
import time
from datetime import timedelta
import hashlib
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.metrics import get_counter, get_histogram

logger = logging.getLogger(__name__)

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


class WompiPaymentClient:
    """
    Cliente para crear transacciones en Wompi (cobros).
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

    def create_pse_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        user_type: int,  # 0=natural, 1=jurídica
        user_legal_id: str,
        user_legal_id_type: str,  # CC, NIT, CE, PP, TI, DNI, RG, OTHER
        financial_institution_code: str,
        payment_description: str,  # Max 30 caracteres
        redirect_url: str | None = None,
        expiration_time: str | None = None,
        taxes: dict | None = None,
        customer_data: dict | None = None,
        shipping_address: dict | None = None,
    ):
        """
        Crea una transacción PSE en Wompi.

        Args:
            amount_in_cents: Monto en centavos
            reference: Referencia única de pago
            customer_email: Email del pagador
            user_type: 0=Persona Natural, 1=Persona Jurídica
            user_legal_id: Número de documento
            user_legal_id_type: Tipo de documento (CC, NIT, CE, PP, TI, DNI, RG, OTHER)
            financial_institution_code: Código del banco PSE
            payment_description: Descripción del pago (max 30 caracteres)
            redirect_url: URL de redirección opcional
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code

        Raises:
            ValueError: Si payment_description excede 30 caracteres
            requests.RequestException: Si falla la comunicación con Wompi

        Example (Sandbox):
            financial_institution_code="1"  # APPROVED
            financial_institution_code="2"  # DECLINED
        """
        if len(payment_description) > 30:
            raise ValueError("payment_description debe tener máximo 30 caracteres para PSE")

        currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        # Generar firma de integridad
        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            expiration_time=expiration_time,
        )

        payload = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "customer_email": customer_email,
            "reference": reference,
            "payment_method": {
                "type": "PSE",
                "user_type": user_type,
                "user_legal_id_type": user_legal_id_type,
                "user_legal_id": user_legal_id,
                "financial_institution_code": financial_institution_code,
                "payment_description": payment_description,
            },
        }

        if signature:
            payload["signature"] = {"integrity": signature}

        if redirect_url:
            payload["redirect_url"] = redirect_url

        if expiration_time:
            payload["expiration_time"] = expiration_time

        if taxes:
            tax_payload = {}
            if taxes.get("vat") is not None:
                tax_payload["vat"] = taxes["vat"]
            if taxes.get("consumption") is not None:
                tax_payload["consumption"] = taxes["consumption"]
            if tax_payload:
                payload["tax_in_cents"] = tax_payload

        if customer_data:
            payload["customer_data"] = {k: v for k, v in customer_data.items() if v not in (None, "")}

        if shipping_address:
            payload["shipping_address"] = {k: v for k, v in shipping_address.items() if v not in (None, "")}

        return self.create_transaction(payload)

    def get_pse_financial_institutions(self):
        """
        Obtiene la lista de instituciones financieras disponibles para PSE.

        Returns:
            list: Lista de bancos con código y nombre

        Example:
            [
                {"financial_institution_code": "1", "financial_institution_name": "Banco que aprueba"},
                {"financial_institution_code": "2", "financial_institution_name": "Banco que rechaza"}
            ]
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/pse/financial_institutions"

        try:
            response = requests.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except requests.Timeout:
            logger.error("Timeout al obtener instituciones financieras PSE")
            raise
        except requests.RequestException as exc:
            logger.exception("Error al obtener instituciones financieras PSE: %s", exc)
            raise

    def create_nequi_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
        taxes: dict | None = None,
        customer_data: dict | None = None,
        shipping_address: dict | None = None,
    ):
        """
        Crea una transacción Nequi en Wompi.

        Args:
            amount_in_cents: Monto en centavos
            reference: Referencia única de pago
            customer_email: Email del pagador
            phone_number: Número de celular Nequi (10 dígitos)
            redirect_url: URL de redirección opcional
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code

        Example (Sandbox):
            phone_number="3991111111"  # APPROVED
            phone_number="3992222222"  # DECLINED
            phone_number="cualquier_otro"  # ERROR
        """
        currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            expiration_time=expiration_time,
        )

        payload = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "customer_email": customer_email,
            "reference": reference,
            "payment_method": {
                "type": "NEQUI",
                "phone_number": phone_number,
            },
        }

        if signature:
            payload["signature"] = {"integrity": signature}

        if redirect_url:
            payload["redirect_url"] = redirect_url

        if expiration_time:
            payload["expiration_time"] = expiration_time

        if taxes:
            tax_payload = {}
            if taxes.get("vat") is not None:
                tax_payload["vat"] = taxes["vat"]
            if taxes.get("consumption") is not None:
                tax_payload["consumption"] = taxes["consumption"]
            if tax_payload:
                payload["tax_in_cents"] = tax_payload

        if customer_data:
            payload["customer_data"] = {k: v for k, v in customer_data.items() if v not in (None, "")}

        if shipping_address:
            payload["shipping_address"] = {k: v for k, v in shipping_address.items() if v not in (None, "")}

        return self.create_transaction(payload)

    def create_daviplata_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
        taxes: dict | None = None,
        customer_data: dict | None = None,
        shipping_address: dict | None = None,
    ):
        """
        Crea una transacción Daviplata en Wompi.

        Args:
            amount_in_cents: Monto en centavos
            reference: Referencia única de pago
            customer_email: Email del pagador
            phone_number: Número de celular Daviplata (10 dígitos)
            redirect_url: URL de redirección opcional
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code

        Example (Sandbox):
            phone_number="3991111111"  # APPROVED
            OTP: 574829 → APPROVED
            OTP: 932015 → DECLINED
            OTP: 186743 → DECLINED sin saldo
            OTP: 999999 → ERROR
        """
        currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            expiration_time=expiration_time,
        )

        payload = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "customer_email": customer_email,
            "reference": reference,
            "payment_method": {
                "type": "DAVIPLATA",
                "phone_number": phone_number,
            },
        }

        if signature:
            payload["signature"] = {"integrity": signature}

        if redirect_url:
            payload["redirect_url"] = redirect_url

        if expiration_time:
            payload["expiration_time"] = expiration_time

        if taxes:
            tax_payload = {}
            if taxes.get("vat") is not None:
                tax_payload["vat"] = taxes["vat"]
            if taxes.get("consumption") is not None:
                tax_payload["consumption"] = taxes["consumption"]
            if tax_payload:
                payload["tax_in_cents"] = tax_payload

        if customer_data:
            payload["customer_data"] = {k: v for k, v in customer_data.items() if v not in (None, "")}

        if shipping_address:
            payload["shipping_address"] = {k: v for k, v in shipping_address.items() if v not in (None, "")}

        return self.create_transaction(payload)

    def create_bancolombia_transfer_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        payment_description: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
        taxes: dict | None = None,
        customer_data: dict | None = None,
        shipping_address: dict | None = None,
    ):
        """
        Crea una transacción Bancolombia Transfer (Botón Bancolombia).

        Args:
            amount_in_cents: Monto en centavos
            reference: Referencia única de pago
            customer_email: Email del pagador
            payment_description: Descripción del pago (max 64 caracteres)
            redirect_url: URL de redirección opcional
            expiration_time: Fecha de expiración en formato ISO8601 UTC

        Returns:
            (dict, int): Response data y status code

        Note:
            La respuesta incluirá async_payment_url donde el usuario
            debe autenticarse con Bancolombia.
        """
        if len(payment_description) > 64:
            raise ValueError("payment_description debe tener máximo 64 caracteres")

        currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        signature = build_integrity_signature(
            reference=reference,
            amount_in_cents=amount_in_cents,
            currency=currency,
            expiration_time=expiration_time,
        )

        payload = {
            "amount_in_cents": amount_in_cents,
            "currency": currency,
            "customer_email": customer_email,
            "reference": reference,
            "payment_method": {
                "type": "BANCOLOMBIA_TRANSFER",
                "payment_description": payment_description,
            },
        }

        if signature:
            payload["signature"] = {"integrity": signature}

        if redirect_url:
            payload["redirect_url"] = redirect_url

        if expiration_time:
            payload["expiration_time"] = expiration_time

        if taxes:
            tax_payload = {}
            if taxes.get("vat") is not None:
                tax_payload["vat"] = taxes["vat"]
            if taxes.get("consumption") is not None:
                tax_payload["consumption"] = taxes["consumption"]
            if tax_payload:
                payload["tax_in_cents"] = tax_payload

        if customer_data:
            payload["customer_data"] = {k: v for k, v in customer_data.items() if v not in (None, "")}

        if shipping_address:
            payload["shipping_address"] = {k: v for k, v in shipping_address.items() if v not in (None, "")}

        return self.create_transaction(payload)

    def tokenize_card(
        self,
        *,
        number: str,
        cvc: str,
        exp_month: str,
        exp_year: str,
        card_holder: str,
    ):
        """
        Tokeniza una tarjeta de crédito para cobros recurrentes.

        Args:
            number: Número de tarjeta (sin espacios)
            cvc: Código de seguridad (3 dígitos)
            exp_month: Mes de expiración (01-12)
            exp_year: Año de expiración (YY o YYYY)
            card_holder: Nombre del titular

        Returns:
            dict: Token de tarjeta

        Example (Sandbox):
            number="4242424242424242"  # APPROVED
            number="4111111111111111"  # DECLINED
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/tokens/cards"

        payload = {
            "number": number.replace(" ", ""),
            "cvc": cvc,
            "exp_month": exp_month.zfill(2),
            "exp_year": exp_year,
            "card_holder": card_holder,
        }

        public_key = getattr(settings, "WOMPI_PUBLIC_KEY", "")
        headers = {"Content-Type": "application/json"}
        if public_key:
            headers["Authorization"] = f"Bearer {public_key}"

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.exception("Error al tokenizar tarjeta: %s", exc)
            raise

    def create_payment_source_from_token(self, token_id: str, customer_email: str, acceptance_token: str):
        """
        Crea una fuente de pago (payment_source) a partir de un token.

        Args:
            token_id: ID del token obtenido de tokenize_card()
            customer_email: Email del cliente
            acceptance_token: Token de aceptación de términos

        Returns:
            dict: Fuente de pago con payment_source_id
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/payment_sources"

        payload = {
            "type": "CARD",
            "token": token_id,
            "customer_email": customer_email,
            "acceptance_token": acceptance_token,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.exception("Error al crear payment source: %s", exc)
            raise

    def tokenize_nequi(self, phone_number: str):
        """
        Tokeniza una cuenta Nequi para cobros recurrentes.

        Args:
            phone_number: Número de celular Nequi (10 dígitos, sin +57)

        Returns:
            dict: Token de Nequi

        Example (Sandbox):
            phone_number="3991111111"  # APPROVED
            
        Response:
            {
                "status": "PENDING",
                "data": {
                    "id": "tok_nequi_123456",
                    "phone_number": "3991111111",
                    "status": "PENDING"
                }
            }
            
        Note:
            El usuario recibirá una notificación push en su app Nequi
            para autorizar la tokenización. El estado final se notificará
            vía webhook (evento: nequi_token.updated).
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/tokens/nequi"

        payload = {"phone_number": phone_number}

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.exception("Error al tokenizar Nequi: %s", exc)
            raise

    def get_nequi_token_status(self, token_id: str):
        """
        Obtiene el estado de un token Nequi.

        Args:
            token_id: ID del token de Nequi

        Returns:
            dict: Estado del token

        Example Response:
            {
                "data": {
                    "id": "tok_nequi_123456",
                    "phone_number": "3991111111",
                    "status": "APPROVED"  # o "DECLINED", "PENDING"
                }
            }
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/tokens/nequi/{token_id}"

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.exception("Error al consultar estado de token Nequi: %s", exc)
            raise
