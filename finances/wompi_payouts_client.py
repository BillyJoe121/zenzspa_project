"""
Cliente para Wompi Payouts API (Pagos a Terceros).

Este módulo implementa el cliente completo para la API de dispersión de pagos de Wompi,
incluyendo:
- Consulta de cuentas origen
- Consulta de bancos
- Creación de órdenes de pago (lotes)
- Consulta de estado de lotes y transacciones
- Sistema de idempotencia
- Manejo de errores y reintentos
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class WompiPayoutsError(Exception):
    """Errores relacionados con Wompi Payouts API."""
    pass


class WompiPayoutsClient:
    """
    Cliente para Wompi Payouts API.

    Documentación: https://docs.wompi.co/docs/payouts-api

    Características:
    - Soporte para sandbox y producción
    - Headers de autenticación correctos (x-api-key, user-principal-id)
    - Sistema de reintentos con backoff exponencial
    - Circuit breaker para proteger contra fallas masivas
    - Idempotencia automática
    - Validaciones bancarias
    """

    REQUEST_TIMEOUT = 30  # Aumentado para operaciones de payout
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 1.0
    _CIRCUIT_CACHE_KEY = "wompi:payouts:circuit"

    # Estados de lotes según documentación
    class BatchStatus:
        PENDING_APPROVAL = "PENDING_APPROVAL"
        PENDING = "PENDING"
        NOT_APPROVED = "NOT_APPROVED"
        REJECTED = "REJECTED"
        PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
        TOTAL_PAYMENT = "TOTAL_PAYMENT"

    # Estados de transacciones según documentación
    class TransactionStatus:
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        CANCELLED = "CANCELLED"
        FAILED = "FAILED"

    def __init__(self):
        """Inicializa el cliente con credenciales desde settings."""
        self.api_key = getattr(settings, "WOMPI_PAYOUT_PRIVATE_KEY", "")
        self.user_id = getattr(settings, "WOMPI_PAYOUT_USER_ID", "")
        self.base_url = (getattr(settings, "WOMPI_PAYOUT_BASE_URL", "") or "").rstrip("/")
        self.mode = getattr(settings, "WOMPI_PAYOUT_MODE", "sandbox")
        self.currency = getattr(settings, "WOMPI_CURRENCY", "COP")

        # Validar configuración
        if not self.api_key or not self.user_id or not self.base_url:
            logger.warning(
                "Wompi Payouts no configurado correctamente. "
                "Verifica WOMPI_PAYOUT_PRIVATE_KEY, WOMPI_PAYOUT_USER_ID y WOMPI_PAYOUT_BASE_URL"
            )

    def _headers(self) -> Dict[str, str]:
        """
        Genera los headers requeridos para Wompi Payouts API.

        Según documentación, se requieren:
        - x-api-key: API Key del comercio
        - user-principal-id: ID del usuario principal
        """
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

    @classmethod
    def _circuit_allows(cls) -> bool:
        """Verifica si el circuit breaker permite requests."""
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        open_until = state.get("open_until")
        if open_until and open_until > timezone.now():
            logger.warning(
                "Circuit breaker abierto hasta %s. Rechazando request.",
                open_until.isoformat()
            )
            return False
        return True

    @classmethod
    def _record_failure(cls, max_failures: int = 5, cooldown_seconds: int = 120):
        """Registra una falla y abre el circuito si se excede el umbral."""
        state = cache.get(cls._CIRCUIT_CACHE_KEY, {"failures": 0, "open_until": None})
        failures = state.get("failures", 0) + 1
        open_until = state.get("open_until")

        if failures >= max_failures:
            open_until = timezone.now() + timedelta(seconds=cooldown_seconds)
            logger.error(
                "Circuit breaker ABIERTO por %d fallas consecutivas. "
                "Bloqueando requests hasta %s",
                failures,
                open_until.isoformat()
            )
            failures = 0  # Reset counter

        cache.set(
            cls._CIRCUIT_CACHE_KEY,
            {"failures": failures, "open_until": open_until},
            timeout=cooldown_seconds + 60
        )

    @classmethod
    def _record_success(cls):
        """Registra un éxito y resetea el circuit breaker."""
        cache.set(
            cls._CIRCUIT_CACHE_KEY,
            {"failures": 0, "open_until": None},
            timeout=300
        )

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> requests.Response:
        """
        Realiza un request HTTP con reintentos y backoff exponencial.

        Args:
            method: GET, POST, etc.
            endpoint: Ruta relativa (ej: '/accounts', '/payouts')
            **kwargs: Parámetros adicionales para requests.request

        Returns:
            Response de requests

        Raises:
            WompiPayoutsError: Si todos los reintentos fallan
        """
        if not self._circuit_allows():
            raise WompiPayoutsError("Circuit breaker abierto. Servicio temporalmente no disponible.")

        url = f"{self.base_url}{endpoint}"
        last_exc = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.debug(
                    "[Wompi Payouts] %s %s (intento %d/%d)",
                    method.upper(),
                    endpoint,
                    attempt,
                    self.MAX_RETRIES
                )

                response = requests.request(
                    method=method,
                    url=url,
                    timeout=self.REQUEST_TIMEOUT,
                    headers=self._headers(),
                    **kwargs
                )

                # Log response para debugging
                logger.debug(
                    "[Wompi Payouts] Response %d: %s",
                    response.status_code,
                    response.text[:500] if response.text else "empty"
                )

                # Wompi puede devolver errores HTTP
                response.raise_for_status()

                # Éxito - resetear circuit breaker
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
                        str(exc)
                    )
                    raise WompiPayoutsError(f"Request falló: {exc}") from exc

                # Backoff exponencial
                sleep_for = self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                logger.warning(
                    "[Wompi Payouts] Error en intento %d/%d: %s. Reintentando en %.1fs",
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                    sleep_for
                )
                time.sleep(sleep_for)

        # Nunca debería llegar aquí, pero por seguridad
        raise WompiPayoutsError(f"Request falló después de {self.MAX_RETRIES} intentos")

    # ==================================================================================
    # MÉTODOS PRINCIPALES DE LA API
    # ==================================================================================

    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de cuentas origen disponibles para dispersión.

        GET /accounts

        Returns:
            Lista de cuentas con estructura:
            [
                {
                    "id": "uuid",
                    "balanceInCents": 1000000,
                    "accountNumber": "1234567890",
                    "bankId": "1007",
                    "accountType": "AHORROS",
                    "status": "ACTIVE"
                },
                ...
            ]
        """
        try:
            response = self._request_with_retry("GET", "/accounts")
            data = response.json()

            # La API devuelve { "data": [...] }
            accounts = data.get("data", [])

            if isinstance(accounts, dict):
                # En algunos casos puede devolver { "accounts": [...] }
                accounts = accounts.get("accounts", [])

            logger.info("[Wompi Payouts] Obtenidas %d cuentas", len(accounts))
            return accounts

        except Exception as exc:
            logger.exception("[Wompi Payouts] Error obteniendo cuentas: %s", exc)
            raise WompiPayoutsError(f"No se pudieron obtener las cuentas: {exc}") from exc

    def get_available_balance(self, account_id: Optional[str] = None) -> Decimal:
        """
        Obtiene el saldo disponible de una cuenta específica o la primera activa.

        Args:
            account_id: ID de la cuenta. Si es None, usa la primera cuenta activa.

        Returns:
            Saldo disponible en COP (Decimal)
        """
        accounts = self.get_accounts()

        if not accounts:
            raise WompiPayoutsError("No hay cuentas disponibles")

        # Buscar cuenta específica o usar la primera
        target_account = None
        if account_id:
            target_account = next((acc for acc in accounts if acc.get("id") == account_id), None)
            if not target_account:
                raise WompiPayoutsError(f"Cuenta {account_id} no encontrada")
        else:
            # Usar primera cuenta activa
            target_account = accounts[0]

        balance_cents = target_account.get("balanceInCents") or target_account.get("balance_in_cents") or 0
        balance = Decimal(balance_cents) / Decimal("100")

        logger.info(
            "[Wompi Payouts] Saldo de cuenta %s: $%s COP",
            target_account.get("id", "unknown"),
            balance
        )

        return balance.quantize(Decimal("0.01"))

    def get_banks(self) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de bancos soportados por Wompi.

        GET /banks

        Returns:
            Lista de bancos con estructura:
            [
                {
                    "id": "1007",
                    "name": "BANCOLOMBIA",
                    "code": "1007"
                },
                ...
            ]
        """
        try:
            response = self._request_with_retry("GET", "/banks")
            data = response.json()

            banks = data.get("data", [])
            logger.info("[Wompi Payouts] Obtenidos %d bancos", len(banks))
            return banks

        except Exception as exc:
            logger.exception("[Wompi Payouts] Error obteniendo bancos: %s", exc)
            raise WompiPayoutsError(f"No se pudieron obtener los bancos: {exc}") from exc

    def create_payout(
        self,
        amount: Decimal,
        reference: str,
        beneficiary_data: Optional[Dict[str, str]] = None,
        account_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Crea una orden de pago (lote con una sola transacción).

        POST /payouts

        Args:
            amount: Monto a dispersar en COP
            reference: Referencia única de la transacción
            beneficiary_data: Datos del beneficiario. Si es None, usa config del desarrollador
            account_id: ID de cuenta origen. Si es None, usa la primera disponible
            idempotency_key: Llave de idempotencia. Si es None, se genera automáticamente

        Returns:
            Tupla (payout_id, response_data)
        """
        # Validar monto
        if amount <= Decimal("0"):
            raise WompiPayoutsError("El monto debe ser mayor a cero")

        # Obtener account_id si no se proporcionó
        if not account_id:
            accounts = self.get_accounts()
            if not accounts:
                raise WompiPayoutsError("No hay cuentas disponibles para dispersión")
            account_id = accounts[0].get("id")

        # Usar datos del desarrollador por defecto
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

        # Validar datos del beneficiario
        self._validate_beneficiary_data(beneficiary_data)

        # Generar idempotency key si no se proporcionó
        if not idempotency_key:
            idempotency_key = self._generate_idempotency_key(reference, amount)

        # Convertir monto a centavos (formato requerido por Wompi)
        amount_in_cents = int(amount * Decimal("100"))

        # Construir payload según documentación de Wompi
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
            logger.info(
                "[Wompi Payouts] Creando payout: $%s COP para %s (ref: %s)",
                amount,
                beneficiary_data.get("name", "unknown"),
                reference
            )

            response = self._request_with_retry("POST", "/payouts", json=payload)
            data = response.json()

            # Extraer ID del lote
            payout_data = data.get("data", {})
            payout_id = payout_data.get("id")

            if not payout_id:
                logger.error("[Wompi Payouts] Response sin ID: %s", data)
                raise WompiPayoutsError("La respuesta de Wompi no incluyó un ID de lote")

            logger.info(
                "[Wompi Payouts] Payout creado exitosamente: ID=%s, Estado=%s",
                payout_id,
                payout_data.get("status", "unknown")
            )

            return payout_id, payout_data

        except Exception as exc:
            logger.exception("[Wompi Payouts] Error creando payout: %s", exc)
            raise WompiPayoutsError(f"No se pudo crear el payout: {exc}") from exc

    def get_payout(self, payout_id: str) -> Dict[str, Any]:
        """
        Consulta el estado de un lote de pago.

        GET /payouts/{payoutId}

        Args:
            payout_id: ID del lote

        Returns:
            Datos del lote incluyendo estado y transacciones
        """
        try:
            response = self._request_with_retry("GET", f"/payouts/{payout_id}")
            data = response.json()
            return data.get("data", {})
        except Exception as exc:
            logger.exception("[Wompi Payouts] Error consultando payout %s: %s", payout_id, exc)
            raise WompiPayoutsError(f"No se pudo consultar el payout: {exc}") from exc

    def get_payout_transactions(self, payout_id: str) -> List[Dict[str, Any]]:
        """
        Consulta las transacciones de un lote específico.

        GET /payouts/{payoutId}/transactions

        Args:
            payout_id: ID del lote

        Returns:
            Lista de transacciones del lote
        """
        try:
            response = self._request_with_retry("GET", f"/payouts/{payout_id}/transactions")
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            logger.exception(
                "[Wompi Payouts] Error consultando transacciones del payout %s: %s",
                payout_id,
                exc
            )
            raise WompiPayoutsError(f"No se pudieron consultar las transacciones: {exc}") from exc

    def get_transaction_by_reference(self, reference: str) -> Optional[Dict[str, Any]]:
        """
        Busca una transacción por su referencia.

        GET /transactions/{reference}

        Args:
            reference: Referencia única de la transacción

        Returns:
            Datos de la transacción o None si no se encuentra
        """
        try:
            response = self._request_with_retry("GET", f"/transactions/{reference}")
            data = response.json()

            transactions = data.get("data", [])
            if transactions:
                return transactions[0]  # Retornar primera coincidencia
            return None

        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                logger.info("[Wompi Payouts] Transacción no encontrada: %s", reference)
                return None
            raise
        except Exception as exc:
            logger.exception(
                "[Wompi Payouts] Error consultando transacción %s: %s",
                reference,
                exc
            )
            raise WompiPayoutsError(f"No se pudo consultar la transacción: {exc}") from exc

    # ==================================================================================
    # MÉTODOS AUXILIARES Y VALIDACIONES
    # ==================================================================================

    @staticmethod
    def _validate_beneficiary_data(data: Dict[str, str]):
        """Valida que los datos del beneficiario sean correctos."""
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

        # Validar tipo de cuenta
        if data["accountType"] not in ["AHORROS", "CORRIENTE"]:
            raise WompiPayoutsError(
                f"accountType inválido: {data['accountType']}. Debe ser AHORROS o CORRIENTE"
            )

        # Validar número de cuenta (6-20 dígitos, solo números)
        account_number = data["accountNumber"]
        if not account_number.isdigit():
            raise WompiPayoutsError("accountNumber debe contener solo números")

        if not (6 <= len(account_number) <= 20):
            raise WompiPayoutsError("accountNumber debe tener entre 6 y 20 dígitos")

        # Validar que no sea todo ceros
        if account_number == "0" * len(account_number):
            raise WompiPayoutsError("accountNumber no puede ser todo ceros")

    @staticmethod
    def _generate_idempotency_key(reference: str, amount: Decimal) -> str:
        """
        Genera una llave de idempotencia única basada en referencia y monto.

        La llave expira en 24 horas según documentación de Wompi.
        """
        # Combinar referencia, monto y fecha para unicidad
        today = timezone.now().date().isoformat()
        raw = f"{reference}:{amount}:{today}"
        hash_value = hashlib.sha256(raw.encode()).hexdigest()[:32]

        # Formato: IDMP-{hash}-{uuid corto}
        short_uuid = str(uuid.uuid4())[:8]
        return f"IDMP-{hash_value}-{short_uuid}"

    # ==================================================================================
    # MÉTODOS SANDBOX (solo para testing)
    # ==================================================================================

    def recharge_balance_sandbox(self, account_id: str, amount: Decimal) -> Dict[str, Any]:
        """
        Recarga saldo en una cuenta de sandbox (solo para testing).

        POST /accounts/balance-recharge

        Args:
            account_id: ID de la cuenta a recargar
            amount: Monto a recargar en COP

        Returns:
            Respuesta de la API

        Note:
            Este endpoint solo funciona en modo sandbox
        """
        if self.mode != "sandbox":
            raise WompiPayoutsError("La recarga de saldo solo está disponible en modo sandbox")

        amount_in_cents = int(amount * Decimal("100"))

        payload = {
            "accountId": account_id,
            "amount": amount_in_cents,
        }

        try:
            logger.info(
                "[Wompi Payouts Sandbox] Recargando $%s COP en cuenta %s",
                amount,
                account_id
            )

            response = self._request_with_retry("POST", "/accounts/balance-recharge", json=payload)
            data = response.json()

            logger.info("[Wompi Payouts Sandbox] Recarga exitosa")
            return data

        except Exception as exc:
            logger.exception("[Wompi Payouts Sandbox] Error recargando saldo: %s", exc)
            raise WompiPayoutsError(f"No se pudo recargar el saldo: {exc}") from exc
