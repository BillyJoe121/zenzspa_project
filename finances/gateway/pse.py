"""
Mixin PSE para WompiPaymentClient.

Contiene:
- PSEMixin: Métodos para transacciones PSE
"""
import logging

import requests
from django.conf import settings

from finances.gateway.base import build_integrity_signature


logger = logging.getLogger(__name__)


class PSEMixin:
    """Mixin con métodos PSE para WompiPaymentClient."""

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
