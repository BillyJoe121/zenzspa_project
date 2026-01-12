from finances.models import PaymentToken, WebhookEvent
from users.models import CustomUser

from .shared import logger


def process_token_update(service):
    """
    Procesa eventos de tokenización (nequi_token.updated, bancolombia_transfer_token.updated).
    Valida la firma y marca el evento como procesado para evitar reintentos.
    """
    try:
        service._validate_signature()
        token_data = service.data.get("token") or service.data.get("data") or {}
        token_id = token_data.get("id") or token_data.get("token")
        token_status = (token_data.get("status") or "").upper() or PaymentToken.TokenStatus.PENDING
        token_type = token_data.get("type") or token_data.get("payment_method_type") or ""
        phone_number = token_data.get("phone_number") or token_data.get("phone") or ""
        customer_email = token_data.get("customer_email") or service.data.get("customer_email") or ""

        linked_user = None
        if customer_email:
            linked_user = CustomUser.objects.filter(email__iexact=customer_email).first()
        if not linked_user and phone_number:
            linked_user = CustomUser.objects.filter(phone_number=phone_number).first()

        if not token_id:
            raise ValueError("No se encontró token_id en el evento de token.")

        fingerprint = PaymentToken.fingerprint(token_id)
        masked = PaymentToken.mask_token(token_id)

        PaymentToken.objects.update_or_create(
            token_fingerprint=fingerprint,
            defaults={
                "token_id": masked,
                "token_secret": token_id,
                "status": token_status,
                "token_type": token_type,
                "phone_number": phone_number or "",
                "customer_email": customer_email or "",
                "raw_payload": service.data,
                "user": linked_user,
            },
        )

        service._update_event_status(WebhookEvent.Status.PROCESSED)
        logger.info(
            "[PAYMENT-SUCCESS] Evento de token procesado (event=%s, token=%s, status=%s)",
            service.event_type,
            masked,
            token_status,
        )
        return {"status": "token_event_processed", "token_id": masked, "token_status": token_status}
    except Exception as exc:
        service._update_event_status(WebhookEvent.Status.FAILED, str(exc))
        logger.error("[PAYMENT-ALERT] Webhook Token Error: %s", exc, exc_info=True)
        raise
