"""
Mixin Billeteras Móviles para WompiPaymentClient.

Contiene:
- MobileWalletsMixin: Métodos para Nequi, Daviplata y Bancolombia Transfer
"""
from django.conf import settings

from finances.gateway.base import build_integrity_signature


class MobileWalletsMixin:
    """Mixin con métodos de billeteras móviles para WompiPaymentClient."""

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
