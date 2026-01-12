from finances.models import WebhookEvent

from .payouts import process_payout_update
from .shared import logger, payment_failures, webhook_signature_errors
from .signature import validate_signature
from .tokens import process_token_update
from .transactions import process_transaction_update

__all__ = ["WompiWebhookService", "webhook_signature_errors", "payment_failures"]


class WompiWebhookService:
    """
    Servicio para procesar y validar webhooks de Wompi.
    """

    def __init__(self, request_data, headers=None):
        if isinstance(request_data, dict):
            self.request_body = request_data
        else:
            try:
                self.request_body = dict(request_data)
            except Exception:
                self.request_body = {}
        self.data = self.request_body.get("data", {})
        self.event_type = self.request_body.get("event")
        self.sent_signature = self.request_body.get("signature", {}).get("checksum")
        self.timestamp = self.request_body.get("timestamp")
        self.headers = headers or {}
        self.event_record = WebhookEvent.objects.create(
            payload=self.request_body,
            headers=dict(self.headers),
            event_type=self.event_type or "",
            status=WebhookEvent.Status.PROCESSED,
        )

    def _validate_signature(self):
        return validate_signature(
            request_body=self.request_body,
            data=self.data,
            event_type=self.event_type,
            timestamp=self.timestamp,
        )

    def _update_event_status(self, status, error_message=None):
        self.event_record.status = status
        self.event_record.error_message = error_message or ""
        self.event_record.save(update_fields=["status", "error_message", "updated_at"])

    def process_transaction_update(self):
        return process_transaction_update(self)

    def process_token_update(self):
        return process_token_update(self)

    def process_payout_update(self):
        return process_payout_update(self)
