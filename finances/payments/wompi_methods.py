"""
Métodos de Pago Wompi.

Contiene funciones para crear transacciones por método:
- create_pse_payment
- create_nequi_payment
- create_daviplata_payment
- create_bancolombia_transfer_payment
"""
from finances.gateway import WompiPaymentClient
from finances.models import Payment
from finances.payments.utils import build_tax_payload, build_customer_data


def create_pse_payment(
    *,
    payment: Payment,
    user_type: int,
    user_legal_id: str,
    user_legal_id_type: str,
    financial_institution_code: str,
    payment_description: str,
    redirect_url: str | None = None,
    expiration_time: str | None = None,
):
    """
    Crea una transacción PSE en Wompi para un pago existente.
    """
    if payment.status != Payment.PaymentStatus.PENDING:
        raise ValueError("El pago debe estar en estado PENDING para crear la transacción PSE")

    if not payment.user:
        raise ValueError("El pago debe tener un usuario asociado")

    client = WompiPaymentClient()
    amount_in_cents = int(payment.amount * 100)

    # Preparar datos opcionales (impuestos y customer_data)
    taxes = build_tax_payload(payment)
    customer_data = build_customer_data(payment)

    # Actualizar campos del modelo Payment
    payment.customer_legal_id = user_legal_id
    payment.customer_legal_id_type = user_legal_id_type
    payment.payment_method_type = "PSE"
    payment.payment_method_data = {
        "financial_institution_code": financial_institution_code,
        "payment_description": payment_description,
        "user_type": user_type,
    }

    response_data, status_code = client.create_pse_transaction(
        amount_in_cents=amount_in_cents,
        reference=payment.transaction_id,
        customer_email=payment.user.email,
        user_type=user_type,
        user_legal_id=user_legal_id,
        user_legal_id_type=user_legal_id_type,
        financial_institution_code=financial_institution_code,
        payment_description=payment_description,
        redirect_url=redirect_url,
        expiration_time=expiration_time,
        taxes=taxes,
        customer_data=customer_data,
    )

    if status_code == 201:
        transaction_data = response_data.get("data", {})
        payment.raw_response = transaction_data
        # Extraer async_payment_url de PSE para redirección
        if "payment_method" in transaction_data:
            extra = transaction_data["payment_method"].get("extra", {})
            if "async_payment_url" in extra:
                payment.payment_method_data["async_payment_url"] = extra["async_payment_url"]

    payment.save(update_fields=[
        'customer_legal_id',
        'customer_legal_id_type',
        'payment_method_type',
        'payment_method_data',
        'raw_response',
        'updated_at'
    ])

    return response_data, status_code


def create_nequi_payment(
    *,
    payment: Payment,
    phone_number: str,
    redirect_url: str | None = None,
    expiration_time: str | None = None,
):
    """
    Crea una transacción Nequi en Wompi para un pago existente.
    """
    if payment.status != Payment.PaymentStatus.PENDING:
        raise ValueError("El pago debe estar en estado PENDING para crear la transacción Nequi")

    if not payment.user:
        raise ValueError("El pago debe tener un usuario asociado")

    client = WompiPaymentClient()
    amount_in_cents = int(payment.amount * 100)

    taxes = build_tax_payload(payment)
    customer_data = build_customer_data(payment)

    # Actualizar campos del modelo Payment
    payment.payment_method_type = "NEQUI"
    payment.payment_method_data = {
        "phone_number": phone_number,
    }

    response_data, status_code = client.create_nequi_transaction(
        amount_in_cents=amount_in_cents,
        reference=payment.transaction_id,
        customer_email=payment.user.email,
        phone_number=phone_number,
        redirect_url=redirect_url,
        expiration_time=expiration_time,
        taxes=taxes,
        customer_data=customer_data,
    )

    if status_code == 201:
        transaction_data = response_data.get("data", {})
        payment.raw_response = transaction_data

    payment.save(update_fields=[
        'payment_method_type',
        'payment_method_data',
        'raw_response',
        'updated_at'
    ])

    return response_data, status_code


def create_daviplata_payment(
    *,
    payment: Payment,
    phone_number: str,
    redirect_url: str | None = None,
    expiration_time: str | None = None,
):
    """Crea una transacción Daviplata en Wompi para un pago existente."""
    if payment.status != Payment.PaymentStatus.PENDING:
        raise ValueError("El pago debe estar en estado PENDING para crear la transacción Daviplata")
    if not payment.user:
        raise ValueError("El pago debe tener un usuario asociado")

    client = WompiPaymentClient()
    amount_in_cents = int(payment.amount * 100)
    taxes = build_tax_payload(payment)
    customer_data = build_customer_data(payment)

    payment.payment_method_type = "DAVIPLATA"
    payment.payment_method_data = {"phone_number": phone_number}

    response_data, status_code = client.create_daviplata_transaction(
        amount_in_cents=amount_in_cents,
        reference=payment.transaction_id,
        customer_email=payment.user.email,
        phone_number=phone_number,
        redirect_url=redirect_url,
        expiration_time=expiration_time,
        taxes=taxes,
        customer_data=customer_data,
    )

    if status_code == 201:
        transaction_data = response_data.get("data", {})
        payment.raw_response = transaction_data

    payment.save(update_fields=[
        'payment_method_type',
        'payment_method_data',
        'raw_response',
        'updated_at'
    ])

    return response_data, status_code


def create_bancolombia_transfer_payment(
    *,
    payment: Payment,
    payment_description: str,
    redirect_url: str | None = None,
    expiration_time: str | None = None,
):
    """Crea una transacción Bancolombia Transfer (Botón) en Wompi para un pago existente."""
    if payment.status != Payment.PaymentStatus.PENDING:
        raise ValueError("El pago debe estar en estado PENDING para crear la transacción Bancolombia Transfer")
    if not payment.user:
        raise ValueError("El pago debe tener un usuario asociado")

    client = WompiPaymentClient()
    amount_in_cents = int(payment.amount * 100)
    taxes = build_tax_payload(payment)
    customer_data = build_customer_data(payment)

    payment.payment_method_type = "BANCOLOMBIA_TRANSFER"
    payment.payment_method_data = {"payment_description": payment_description}

    response_data, status_code = client.create_bancolombia_transfer_transaction(
        amount_in_cents=amount_in_cents,
        reference=payment.transaction_id,
        customer_email=payment.user.email,
        payment_description=payment_description,
        redirect_url=redirect_url,
        expiration_time=expiration_time,
        taxes=taxes,
        customer_data=customer_data,
    )

    if status_code == 201:
        transaction_data = response_data.get("data", {})
        payment.raw_response = transaction_data
        # async_payment_url puede venir en extra o en payment_method directamente
        async_url = None
        payment_method = transaction_data.get("payment_method", {})
        extra = payment_method.get("extra", {}) if isinstance(payment_method, dict) else {}
        async_url = (
            payment_method.get("async_payment_url")
            if isinstance(payment_method, dict)
            else None
        )
        if not async_url:
            async_url = extra.get("async_payment_url")
        if async_url:
            payment.payment_method_data["async_payment_url"] = async_url

    payment.save(update_fields=[
        'payment_method_type',
        'payment_method_data',
        'raw_response',
        'updated_at'
    ])

    return response_data, status_code
