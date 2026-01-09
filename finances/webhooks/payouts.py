import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from finances.models import CommissionLedger, WebhookEvent

from .shared import logger


class WompiPayoutsWebhookService:
    """
    Servicio para validar y procesar webhooks de Wompi Payouts API.
    """
    
    @staticmethod
    def validate_signature(payload: dict, signature: str) -> bool:
        """
        Valida la firma HMAC SHA256 del webhook de payouts.
        
        Args:
            payload: Diccionario con el payload del webhook
            signature: Firma recibida en el header X-Signature
            
        Returns:
            True si la firma es válida, False en caso contrario
        """
        secret = getattr(settings, 'WOMPI_PAYOUT_EVENTS_SECRET', '')
        if not secret:
            logger.error("[Wompi Payouts Webhook] WOMPI_PAYOUT_EVENTS_SECRET no configurado")
            return False
        
        try:
            # Convertir payload a JSON string ordenado
            payload_str = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            
            # Calcular HMAC SHA256
            calculated = hmac.new(
                secret.encode('utf-8'),
                payload_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Comparar de forma segura
            return hmac.compare_digest(calculated.lower(), signature.lower())
        except Exception as exc:
            logger.error("[Wompi Payouts Webhook] Error validando firma: %s", exc)
            return False
    
    @staticmethod
    @transaction.atomic
    def process_event(event_type: str, payload: dict) -> dict:
        """
        Procesa un evento de webhook de payouts.
        
        Args:
            event_type: Tipo de evento (payout.updated, transaction.updated)
            payload: Payload completo del webhook
            
        Returns:
            Diccionario con el resultado del procesamiento
        """
        data = payload.get("data", {})
        
        if event_type in {"payout.updated", "transaction.updated"}:
            return WompiPayoutsWebhookService._process_payout_update(data)
        
        logger.warning("[Wompi Payouts Webhook] Evento no manejado: %s", event_type)
        return {"status": "event_not_handled", "event_type": event_type}
    
    @staticmethod
    def _process_payout_update(data: dict) -> dict:
        """
        Procesa eventos de payout/transfer (dispersión) para reflejar estado final.
        """
        transfer_id = data.get("id") or data.get("transfer_id")
        status_str = (data.get("status") or "").upper()
        
        if not transfer_id or not status_str:
            raise ValueError("transfer_id o status no presentes en el webhook de payout.")
        
        # Actualizar las comisiones asociadas al transfer_id
        entries = CommissionLedger.objects.select_for_update().filter(wompi_transfer_id=transfer_id)
        updated = 0
        now = timezone.now()
        
        for entry in entries:
            if status_str == "APPROVED":
                entry.status = CommissionLedger.Status.PAID
                entry.paid_at = entry.paid_at or now
            elif status_str in {"DECLINED", "ERROR"}:
                entry.status = CommissionLedger.Status.FAILED_NSF
            entry.save(update_fields=["status", "paid_at", "updated_at"])
            updated += 1
        
        logger.info(
            "[PAYMENT-SUCCESS] Evento de payout procesado (transfer_id=%s, status=%s, entries_updated=%s)",
            transfer_id,
            status_str,
            updated,
        )
        
        return {
            "status": "payout_event_processed",
            "transfer_id": transfer_id,
            "transfer_status": status_str,
            "entries_updated": updated
        }


# Mantener función legacy para compatibilidad
@transaction.atomic
def process_payout_update(service):
    """
    Procesa eventos de payout/transfer (dispersión) para reflejar estado final.
    LEGACY: Esta función existe para compatibilidad con código anterior.
    """
    try:
        service._validate_signature()

        transfer_data = service.data.get("transfer") or service.data.get("data") or {}
        transfer_id = transfer_data.get("id") or transfer_data.get("transfer_id")
        status = (transfer_data.get("status") or "").upper()

        if not transfer_id or not status:
            raise ValueError("transfer_id o status no presentes en el webhook de payout.")

        # Actualizar las comisiones asociadas al transfer_id
        entries = CommissionLedger.objects.select_for_update().filter(wompi_transfer_id=transfer_id)
        updated = 0
        now = timezone.now()
        for entry in entries:
            previous_status = entry.status
            if status == "APPROVED":
                entry.status = CommissionLedger.Status.PAID
                entry.paid_at = entry.paid_at or now
            elif status in {"DECLINED", "ERROR"}:
                entry.status = CommissionLedger.Status.FAILED_NSF
            entry.save(update_fields=["status", "paid_at", "updated_at"])
            updated += 1

        service._update_event_status(WebhookEvent.Status.PROCESSED)
        logger.info(
            "[PAYMENT-SUCCESS] Evento de payout procesado (transfer_id=%s, status=%s, entries_updated=%s)",
            transfer_id,
            status,
            updated,
        )
        return {"status": "payout_event_processed", "transfer_id": transfer_id, "transfer_status": status, "entries_updated": updated}
    except Exception as exc:
        service._update_event_status(WebhookEvent.Status.FAILED, str(exc))
        logger.error("[PAYMENT-ALERT] Webhook Payout Error: %s", exc, exc_info=True)
        raise
