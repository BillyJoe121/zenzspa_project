# finances/gateway_extensions.py
"""
Extensiones adicionales para WompiPaymentClient.
Métodos de pago adicionales: Daviplata, Bancolombia, Tokenización.
"""

import logging
import requests
from django.conf import settings
from .gateway import WompiPaymentClient, build_integrity_signature

logger = logging.getLogger(__name__)


class WompiPaymentClientExtended(WompiPaymentClient):
    """
    Extensión de WompiPaymentClient con métodos adicionales.
    Incluye: Daviplata, Bancolombia Transfer, Tokenización de tarjetas.
    """

    def create_daviplata_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
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

        return self.create_transaction(payload)

    def create_bancolombia_transfer_transaction(
        self,
        *,
        amount_in_cents: int,
        reference: str,
        customer_email: str,
        payment_description: str,  # Max 64 caracteres
        redirect_url: str | None = None,
        expiration_time: str | None = None,
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
            La respuesta incluirá async_payment_url en data.payment_method.extra.async_payment_url
            donde el usuario debe autenticarse con Bancolombia.

        Example Response:
            {
                "data": {
                    "id": "11004-1718123303-80111",
                    "payment_method": {
                        "type": "BANCOLOMBIA_TRANSFER",
                        "extra": {
                            "async_payment_url": "https://..."
                        }
                    }
                }
            }
        """
        if len(payment_description) > 64:
            raise ValueError("payment_description debe tener máximo 64 caracteres para Bancolombia Transfer")

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

        Response:
            {
                "status": "CREATED",
                "data": {
                    "id": "tok_prod_123456_abcdef",
                    "created_at": "2023-06-09T20:28:50.000Z",
                    "brand": "VISA",
                    "name": "VISA-4242",
                    "last_four": "4242",
                    "bin": "424242",
                    "exp_year": "25",
                    "exp_month": "12",
                    "card_holder": "Juan Perez"
                }
            }
        """
        if not self.base_url:
            raise ValueError("WOMPI_BASE_URL no configurada")

        url = f"{self.base_url.rstrip('/')}/tokens/cards"

        payload = {
            "number": number.replace(" ", ""),  # Remover espacios
            "cvc": cvc,
            "exp_month": exp_month.zfill(2),  # Asegurar 2 dígitos
            "exp_year": exp_year,
            "card_holder": card_holder,
        }

        # Tokenización usa llave pública, no privada
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
        Crea una fuente de pago (payment_source) a partir de un token de tarjeta.

        Args:
            token_id: ID del token de tarjeta obtenido de tokenize_card()
            customer_email: Email del cliente
            acceptance_token: Token de aceptación de términos

        Returns:
            dict: Fuente de pago creada con payment_source_id

        Note:
            El payment_source_id es necesario para cobros recurrentes

        Response:
            {
                "status": "CREATED",
                "data": {
                    "id": 12345,  # Este es el payment_source_id
                    "type": "CARD",
                    "status": "AVAILABLE",
                    "created_at": "2023-06-09T20:28:50.000Z"
                }
            }
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
