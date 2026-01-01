"""
Webhook handler para eventos de Wompi Payouts API.

Este módulo procesa eventos enviados por Wompi cuando cambia el estado
de un payout o transacción de dispersión.

Eventos soportados:
- payout.updated: Cambio de estado en un lote de pago
- transaction.updated: Cambio de estado en una transacción individual
"""
import hashlib
import hmac
import logging
from typing import Dict, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from core.utils import safe_audit_log
from .models import CommissionLedger

logger = logging.getLogger(__name__)


class WompiPayoutsWebhookError(Exception):
    """Errores en el procesamiento de webhooks de Wompi Payouts."""
    pass


class WompiPayoutsWebhookService:
    """
    Servicio para procesar webhooks de Wompi Payouts API.

    Wompi envía eventos cuando:
    - Un lote de pago cambia de estado (PENDING → TOTAL_PAYMENT, etc.)
    - Una transacción individual cambia de estado (PENDING → APPROVED/FAILED)

    Documentación: https://docs.wompi.co/docs/payouts-api#webhooks
    """

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

    @classmethod
    def validate_signature(cls, payload: Dict[str, Any], signature: str) -> bool:
        """
        Valida que el webhook provenga realmente de Wompi.

        Args:
            payload: Datos del evento
            signature: Firma recibida en el header

        Returns:
            True si la firma es válida, False en caso contrario
        """
        secret = getattr(settings, "WOMPI_PAYOUT_EVENTS_SECRET", "")

        if not secret:
            logger.warning(
                "WOMPI_PAYOUT_EVENTS_SECRET no configurado. "
                "No se puede validar la firma del webhook."
            )
            # En desarrollo podemos permitirlo, en producción NO
            return not settings.DEBUG

        try:
            # Wompi envía la firma como SHA256 HMAC del payload completo
            import json
            payload_string = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as exc:
            logger.exception("Error validando firma del webhook: %s", exc)
            return False

    @classmethod
    def process_event(cls, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa un evento de webhook de Wompi Payouts.

        Args:
            event_type: Tipo de evento (payout.updated, transaction.updated)
            payload: Datos del evento

        Returns:
            Resultado del procesamiento
        """
        logger.info(
            "[Wompi Payouts Webhook] Procesando evento: %s",
            event_type
        )

        # Registrar el evento en audit log
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            details={
                "action": "wompi_payouts_webhook_received",
                "event_type": event_type,
                "payload": payload,
                "timestamp": timezone.now().isoformat(),
            }
        )

        # Routing por tipo de evento
        if event_type == "payout.updated":
            return cls._handle_payout_updated(payload)
        elif event_type == "transaction.updated":
            return cls._handle_transaction_updated(payload)
        else:
            logger.warning(
                "[Wompi Payouts Webhook] Tipo de evento desconocido: %s",
                event_type
            )
            return {"status": "ignored", "reason": "unknown_event_type"}

    @classmethod
    @transaction.atomic
    def _handle_payout_updated(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa evento de actualización de lote de pago.

        Estructura esperada:
        {
            "event": "payout.updated",
            "data": {
                "id": "payout-uuid",
                "status": "TOTAL_PAYMENT",
                "accountId": "account-uuid",
                "createdAt": "2025-12-31T12:00:00Z",
                ...
            }
        }
        """
        data = payload.get("data", {})
        payout_id = data.get("id")
        payout_status = data.get("status")

        if not payout_id or not payout_status:
            logger.error(
                "[Wompi Payouts Webhook] Evento payout.updated sin ID o status: %s",
                payload
            )
            return {"status": "error", "reason": "missing_required_fields"}

        logger.info(
            "[Wompi Payouts Webhook] Lote %s cambió a estado: %s",
            payout_id,
            payout_status
        )

        # Por ahora solo registramos el evento
        # En el futuro podríamos actualizar un modelo PayoutBatch si lo creamos
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            details={
                "action": "payout_status_updated",
                "payout_id": payout_id,
                "new_status": payout_status,
                "timestamp": timezone.now().isoformat(),
            }
        )

        return {
            "status": "processed",
            "payout_id": payout_id,
            "new_status": payout_status
        }

    @classmethod
    @transaction.atomic
    def _handle_transaction_updated(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa evento de actualización de transacción individual.

        Estructura esperada:
        {
            "event": "transaction.updated",
            "data": {
                "id": "transaction-uuid",
                "status": "APPROVED",
                "reference": "DEV-COMM-20251231-120000",
                "amount": 5000000,  // en centavos
                "payoutId": "payout-uuid",
                ...
            }
        }
        """
        data = payload.get("data", {})
        transaction_id = data.get("id")
        transaction_status = data.get("status")
        reference = data.get("reference", "")
        payout_id = data.get("payoutId")

        if not transaction_id or not transaction_status:
            logger.error(
                "[Wompi Payouts Webhook] Evento transaction.updated sin ID o status: %s",
                payload
            )
            return {"status": "error", "reason": "missing_required_fields"}

        logger.info(
            "[Wompi Payouts Webhook] Transacción %s (ref: %s) cambió a estado: %s",
            transaction_id,
            reference,
            transaction_status
        )

        # Buscar comisiones asociadas al payout
        if payout_id:
            ledgers = CommissionLedger.objects.filter(
                wompi_transfer_id=payout_id
            ).select_for_update()

            updated_count = 0

            for ledger in ledgers:
                previous_status = ledger.status

                # Actualizar estado según el estado de la transacción
                if transaction_status == cls.TransactionStatus.APPROVED:
                    # Transacción exitosa - marcar como PAID si no lo está
                    if ledger.status != CommissionLedger.Status.PAID:
                        ledger.status = CommissionLedger.Status.PAID
                        if not ledger.paid_at:
                            ledger.paid_at = timezone.now()
                        ledger.save(update_fields=['status', 'paid_at', 'updated_at'])
                        updated_count += 1

                        logger.info(
                            "[Wompi Payouts Webhook] Comisión %s marcada como PAID",
                            ledger.id
                        )

                elif transaction_status == cls.TransactionStatus.FAILED:
                    # Transacción falló - marcar como FAILED_NSF
                    if ledger.status != CommissionLedger.Status.FAILED_NSF:
                        ledger.status = CommissionLedger.Status.FAILED_NSF
                        ledger.save(update_fields=['status', 'updated_at'])
                        updated_count += 1

                        logger.warning(
                            "[Wompi Payouts Webhook] Comisión %s marcada como FAILED (transacción rechazada)",
                            ledger.id
                        )

                # Registrar el cambio en audit log
                if previous_status != ledger.status:
                    safe_audit_log(
                        action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                        details={
                            "action": "commission_status_updated_by_webhook",
                            "ledger_id": str(ledger.id),
                            "previous_status": previous_status,
                            "new_status": ledger.status,
                            "transaction_id": transaction_id,
                            "payout_id": payout_id,
                            "wompi_status": transaction_status,
                        }
                    )

            if updated_count > 0:
                logger.info(
                    "[Wompi Payouts Webhook] Actualizadas %d comisión(es) para payout %s",
                    updated_count,
                    payout_id
                )

            return {
                "status": "processed",
                "transaction_id": transaction_id,
                "payout_id": payout_id,
                "new_status": transaction_status,
                "ledgers_updated": updated_count
            }
        else:
            # No tenemos payout_id, no podemos actualizar comisiones
            logger.warning(
                "[Wompi Payouts Webhook] Transacción %s sin payoutId, no se pueden actualizar comisiones",
                transaction_id
            )

            # Solo registrar el evento
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details={
                    "action": "transaction_updated_no_payout_id",
                    "transaction_id": transaction_id,
                    "reference": reference,
                    "status": transaction_status,
                }
            )

            return {
                "status": "processed",
                "transaction_id": transaction_id,
                "new_status": transaction_status,
                "warning": "no_payout_id"
            }
