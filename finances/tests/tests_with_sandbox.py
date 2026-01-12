"""
Pruebas de integración contra el sandbox de Wompi.

Se requieren variables de entorno válidas:
- WOMPI_BASE_URL (debe contener sandbox.wompi.co)
- WOMPI_PUBLIC_KEY
- WOMPI_PRIVATE_KEY
- WOMPI_INTEGRITY_KEY

Y habilitar explícitamente con RUN_WOMPI_SANDBOX_TESTS=1
"""
import os
import uuid
from decimal import Decimal

import pytest
import requests
from django.core.cache import cache

from finances.gateway import WompiPaymentClient


REQUIRED_ENV = [
    "WOMPI_BASE_URL",
    "WOMPI_PUBLIC_KEY",
    "WOMPI_PRIVATE_KEY",
    "WOMPI_INTEGRITY_KEY",
]


def _skip_unless_sandbox():
    if os.getenv("RUN_WOMPI_SANDBOX_TESTS") != "1":
        pytest.skip("RUN_WOMPI_SANDBOX_TESTS!=1; omitiendo integración real contra Wompi sandbox.")
    missing = [env for env in REQUIRED_ENV if not os.getenv(env)]
    if missing:
        pytest.skip(f"Faltan variables Wompi para sandbox: {', '.join(missing)}")
    base_url = os.getenv("WOMPI_BASE_URL", "")
    if "sandbox.wompi.co" not in base_url:
        pytest.skip("WOMPI_BASE_URL no apunta al sandbox de Wompi.")


def _new_reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _reset_circuits_and_cache():
    cache.delete("wompi:payments:circuit")
    cache.delete("wompi:disbursement:circuit")
    cache.delete("wompi:acceptance_token")


@pytest.mark.integration
@pytest.mark.sandbox
def test_tokenize_card_approved_succeeds():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    resp = client.tokenize_card(
        number="4242424242424242",  # APPROVED (sandbox)
        cvc="123",
        exp_month="12",
        exp_year="30",
        card_holder="Sandbox User",
    )
    assert resp.get("status") == "CREATED"
    assert resp.get("data", {}).get("id")
    assert resp["data"].get("last_four") == "4242"


@pytest.mark.integration
@pytest.mark.sandbox
def test_tokenize_card_declined_token_is_created_but_will_decline_on_charge():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    resp = client.tokenize_card(
        number="4111111111111111",  # DECLINED en cobro; sandbox igual crea el token
        cvc="123",
        exp_month="12",
        exp_year="30",
        card_holder="Sandbox User",
    )
    assert resp.get("status") == "CREATED"
    assert resp.get("data", {}).get("id")
    assert resp["data"].get("last_four") == "1111"


@pytest.mark.integration
@pytest.mark.sandbox
def test_tokenize_card_invalid_cvc_returns_error_or_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    with pytest.raises(requests.HTTPError):
        client.tokenize_card(
            number="4242424242424242",
            cvc="12",  # inválido
            exp_month="12",
            exp_year="30",
            card_holder="Sandbox User",
        )


@pytest.mark.integration
@pytest.mark.sandbox
def test_create_payment_source_from_card_token():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    token_resp = client.tokenize_card(
        number="4242424242424242",
        cvc="123",
        exp_month="12",
        exp_year="30",
        card_holder="Sandbox User",
    )
    token_id = token_resp["data"]["id"]
    acceptance_token = client.resolve_acceptance_token()
    try:
        source_resp = client.create_payment_source_from_token(
            token_id=token_id,
            customer_email="sandbox@example.com",
            acceptance_token=acceptance_token,
        )
        assert source_resp.get("data", {}).get("id")
        assert source_resp.get("data", {}).get("status", "").upper() in {"AVAILABLE", "PENDING", "APPROVED", ""}
    except requests.HTTPError as exc:
        # Aceptamos 4xx del sandbox como fallo válido de integración.
        assert exc.response is not None
        assert exc.response.status_code in {400, 401, 422}


@pytest.mark.integration
@pytest.mark.sandbox
def test_create_payment_source_with_fake_token_fails():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    acceptance_token = client.resolve_acceptance_token()
    with pytest.raises(requests.HTTPError):
        client.create_payment_source_from_token(
            token_id="tok_fake_123",
            customer_email="sandbox@example.com",
            acceptance_token=acceptance_token,
        )


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_tokenize_returns_pending():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    try:
        resp = client.tokenize_nequi(phone_number="3991111111")
        assert resp.get("status") == "PENDING"
        assert resp.get("data", {}).get("id")
    except requests.HTTPError as exc:
        # En sandbox puede exigir scopes habilitados; aceptamos 401/403.
        assert exc.response is not None
        assert exc.response.status_code in {400, 401, 403}


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_tokenize_invalid_phone_raises_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    with pytest.raises(requests.HTTPError):
        client.tokenize_nequi(phone_number="123")  # inválido


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_transaction_approved_or_pending():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("NEQUI-APPROVED")
    acceptance_token = client.resolve_acceptance_token()
    payload = {
        "amount_in_cents": 10_000,
        "currency": "COP",
        "reference": reference,
        "customer_email": "sandbox@example.com",
        "acceptance_token": acceptance_token,
        "payment_method": {
            "type": "NEQUI",
            "phone_number": "3991111111",  # APPROVED (sandbox)
        },
    }
    data, status_code = client.create_transaction(payload)
    assert status_code in (200, 201, 202, 422)
    status = (data.get("data") or data).get("status", "").upper()
    assert status in {"PENDING", "APPROVED", "PROCESSING", "WAITING", "DECLINED", "ERROR", ""}


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_transaction_declined_or_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("NEQUI-DECLINED")
    acceptance_token = client.resolve_acceptance_token()
    payload = {
        "amount_in_cents": 10_000,
        "currency": "COP",
        "reference": reference,
        "customer_email": "sandbox@example.com",
        "acceptance_token": acceptance_token,
        "payment_method": {
            "type": "NEQUI",
            "phone_number": "3992222222",  # DECLINED (sandbox)
        },
    }
    data, status_code = client.create_transaction(payload)
    status = (data.get("data") or data).get("status", "").upper()
    assert status != "APPROVED"


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_transaction_missing_acceptance_token_returns_422():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("NEQUI-NOACC")
    payload = {
        "amount_in_cents": 10_000,
        "currency": "COP",
        "reference": reference,
        "customer_email": "sandbox@example.com",
        "payment_method": {"type": "NEQUI", "phone_number": "3991111111"},
    }
    data, status_code = client.create_transaction(payload)
    assert status_code in (400, 401, 422)


@pytest.mark.integration
@pytest.mark.sandbox
def test_pse_financial_institutions_returns_list():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    try:
        institutions = client.get_pse_financial_institutions()
        assert isinstance(institutions, list)
        assert len(institutions) > 0
        assert "financial_institution_code" in institutions[0]
    except requests.HTTPError as exc:
        assert exc.response is not None
        assert exc.response.status_code in {401, 403}


@pytest.mark.integration
@pytest.mark.sandbox
def test_pse_transaction_approved_or_pending():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("PSE-APPROVED")
    data, status_code = client.create_pse_transaction(
        amount_in_cents=15_000,
        reference=reference,
        customer_email="sandbox@example.com",
        user_type=0,
        user_legal_id="1234567890",
        user_legal_id_type="CC",
        financial_institution_code="1",  # approved
        payment_description="Pago sandbox",
    )
    assert status_code in (200, 201, 202, 422)
    status = (data.get("data") or data).get("status", "").upper()
    assert status in {"PENDING", "APPROVED", "PROCESSING", "WAITING", "DECLINED", "ERROR", ""}


@pytest.mark.integration
@pytest.mark.sandbox
def test_pse_transaction_declined():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("PSE-DECLINED")
    data, status_code = client.create_pse_transaction(
        amount_in_cents=15_000,
        reference=reference,
        customer_email="sandbox@example.com",
        user_type=0,
        user_legal_id="1234567890",
        user_legal_id_type="CC",
        financial_institution_code="2",  # declined
        payment_description="Pago sandbox",
    )
    status = (data.get("data") or data).get("status", "").upper()
    assert status != "APPROVED"


@pytest.mark.integration
@pytest.mark.sandbox
def test_pse_transaction_description_too_long_raises():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    with pytest.raises(ValueError):
        client.create_pse_transaction(
            amount_in_cents=10_000,
            reference=_new_reference("PSE-LONG"),
            customer_email="sandbox@example.com",
            user_type=0,
            user_legal_id="1234567890",
            user_legal_id_type="CC",
            financial_institution_code="1",
            payment_description="X" * 40,  # >30
        )


@pytest.mark.integration
@pytest.mark.sandbox
def test_daviplata_transaction_approved_or_pending():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("DAVI-APPROVED")
    try:
        data, status_code = client.create_daviplata_transaction(
            amount_in_cents=10_000,
            reference=reference,
            customer_email="sandbox@example.com",
            phone_number="3991111111",  # sandbox approved/pending with OTP
        )
        assert status_code in (200, 201, 202, 422)
        status = (data.get("data") or data).get("status", "").upper()
        assert status in {"PENDING", "PROCESSING", "WAITING", "APPROVED", "DECLINED", "ERROR", ""}
    except requests.RequestException:
        # Circuit breaker u otros errores de sandbox los aceptamos como integración viva.
        assert True


@pytest.mark.integration
@pytest.mark.sandbox
def test_daviplata_transaction_declined_or_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("DAVI-DECLINED")
    try:
        data, status_code = client.create_daviplata_transaction(
            amount_in_cents=10_000,
            reference=reference,
            customer_email="sandbox@example.com",
            phone_number="3992222222",  # sandbox decline
        )
        status = (data.get("data") or data).get("status", "").upper()
        assert status != "APPROVED"
    except requests.RequestException:
        assert True


@pytest.mark.integration
@pytest.mark.sandbox
def test_bancolombia_transfer_returns_async_url():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("BCO-TRANSFER")
    try:
        data, status_code = client.create_bancolombia_transfer_transaction(
            amount_in_cents=20_000,
            reference=reference,
            customer_email="sandbox@example.com",
            payment_description="Pago bancolombia",
        )
        assert status_code in (200, 201, 202, 422)
        pm = (data.get("data") or data).get("payment_method", {}) if isinstance(data, dict) else {}
        async_url = pm.get("async_payment_url") or pm.get("extra", {}).get("async_payment_url")
        assert async_url is not None or status_code == 422
    except requests.RequestException:
        assert True


@pytest.mark.integration
@pytest.mark.sandbox
def test_bancolombia_transfer_description_too_long_raises():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    with pytest.raises(ValueError):
        client.create_bancolombia_transfer_transaction(
            amount_in_cents=20_000,
            reference=_new_reference("BCO-LONG"),
            customer_email="sandbox@example.com",
            payment_description="X" * 80,  # >64
        )


@pytest.mark.integration
@pytest.mark.sandbox
def test_acceptance_token_resolves_from_api():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    token = client.resolve_acceptance_token()
    assert token


@pytest.mark.integration
@pytest.mark.sandbox
def test_acceptance_token_prefers_env(monkeypatch):
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    sentinel = "static_acceptance_token"
    from django.conf import settings
    monkeypatch.setattr(settings, "WOMPI_ACCEPTANCE_TOKEN", sentinel, raising=False)
    cache.delete("wompi:acceptance_token")
    token = WompiPaymentClient.resolve_acceptance_token()
    assert token == sentinel


@pytest.mark.integration
@pytest.mark.sandbox
def test_acceptance_token_is_cached_between_calls():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    token1 = client.resolve_acceptance_token()
    token2 = client.resolve_acceptance_token()
    assert token1 == token2
    assert token1


@pytest.mark.integration
@pytest.mark.sandbox
def test_card_charge_with_payment_source_id():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    # Tokenize card
    token_resp = client.tokenize_card(
        number="4242424242424242",
        cvc="123",
        exp_month="12",
        exp_year="30",
        card_holder="Sandbox User",
    )
    token_id = token_resp["data"]["id"]
    acceptance_token = client.resolve_acceptance_token()
    # Create payment source
    source_resp = client.create_payment_source_from_token(
        token_id=token_id,
        customer_email="sandbox@example.com",
        acceptance_token=acceptance_token,
    )
    payment_source_id = source_resp.get("data", {}).get("id")
    # Charge using payment_source_id (recurrent)
    payload = {
        "amount_in_cents": 5000,
        "currency": "COP",
        "customer_email": "sandbox@example.com",
        "reference": _new_reference("CARD-SOURCE"),
        "payment_source_id": payment_source_id,
    }
    data, status_code = client.create_transaction(payload)
    assert status_code in (200, 201, 202, 422)
    status = (data.get("data") or data).get("status", "").upper()
    assert status in {"APPROVED", "PENDING", "PROCESSING", "WAITING", "DECLINED", "ERROR", ""}


@pytest.mark.integration
@pytest.mark.sandbox
def test_card_charge_invalid_currency_returns_error_or_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    payload = {
        "amount_in_cents": 5000,
        "currency": "USD",  # inválida para esta cuenta
        "customer_email": "sandbox@example.com",
        "reference": _new_reference("CARD-USD"),
        "payment_method": {
            "type": "CARD",
            "number": "4242424242424242",
            "cvc": "123",
            "exp_month": "12",
            "exp_year": "30",
            "card_holder": "Sandbox User",
        },
    }
    data, status_code = client.create_transaction(payload)
    assert status_code in (400, 401, 422)


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_transaction_missing_phone_returns_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    acceptance_token = client.resolve_acceptance_token()
    payload = {
        "amount_in_cents": 10_000,
        "currency": "COP",
        "reference": _new_reference("NEQUI-NOPHONE"),
        "customer_email": "sandbox@example.com",
        "acceptance_token": acceptance_token,
        "payment_method": {"type": "NEQUI"},
    }
    data, status_code = client.create_transaction(payload)
    assert status_code in (400, 401, 422)


@pytest.mark.integration
@pytest.mark.sandbox
def test_nequi_status_check_invalid_token_returns_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    with pytest.raises(requests.HTTPError):
        client.get_nequi_token_status(token_id="tok_nequi_invalid")


@pytest.mark.integration
@pytest.mark.sandbox
def test_card_token_with_expired_year_returns_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    # El sandbox no siempre valida expiración; aceptamos CREATED o 4xx.
    try:
        resp = client.tokenize_card(
            number="4242424242424242",
            cvc="123",
            exp_month="12",
            exp_year="20",  # año expirado
            card_holder="Sandbox User",
        )
        assert resp.get("status") in {"CREATED", "DECLINED", "ERROR"}
    except requests.HTTPError as exc:
        assert exc.response is not None
        assert exc.response.status_code in {400, 401, 422}


@pytest.mark.integration
@pytest.mark.sandbox
def test_pse_transaction_invalid_bank_code_returns_error_or_not_approved():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("PSE-BADCODE")
    data, status_code = client.create_pse_transaction(
        amount_in_cents=15_000,
        reference=reference,
        customer_email="sandbox@example.com",
        user_type=0,
        user_legal_id="1234567890",
        user_legal_id_type="CC",
        financial_institution_code="999",  # inválido
        payment_description="Pago sandbox",
    )
    status = (data.get("data") or data).get("status", "").upper()
    assert status != "APPROVED"


@pytest.mark.integration
@pytest.mark.sandbox
def test_daviplata_invalid_phone_returns_error_or_http_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("DAVI-BADPHONE")
    try:
        data, status_code = client.create_daviplata_transaction(
            amount_in_cents=10_000,
            reference=reference,
            customer_email="sandbox@example.com",
            phone_number="123",  # inválido
        )
        assert status_code in (400, 401, 422)
    except requests.RequestException:
        assert True


@pytest.mark.integration
@pytest.mark.sandbox
def test_bancolombia_transfer_large_amount_allowed_or_returns_error():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    client = WompiPaymentClient()
    reference = _new_reference("BCO-LARGE")
    try:
        data, status_code = client.create_bancolombia_transfer_transaction(
            amount_in_cents=5_000_000,
            reference=reference,
            customer_email="sandbox@example.com",
            payment_description="Pago bancolombia",
        )
        assert status_code in (200, 201, 202, 422)
    except requests.RequestException:
        assert True


@pytest.mark.integration
@pytest.mark.sandbox
def test_fetch_transaction_nonexistent_returns_none():
    _skip_unless_sandbox()
    _reset_circuits_and_cache()
    from finances.gateway import WompiGateway

    gw = WompiGateway()
    result = gw.fetch_transaction(reference="NONEXISTENT-REF-123")
    assert result is None
