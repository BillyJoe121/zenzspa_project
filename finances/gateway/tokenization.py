"""
Mixin Tokenización para WompiPaymentClient.

Contiene:
- TokenizationMixin: Métodos para tokenizar tarjetas y Nequi
"""
import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class TokenizationMixin:
    """Mixin con métodos de tokenización para WompiPaymentClient."""

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
