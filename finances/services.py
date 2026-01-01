from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import GlobalSettings, AuditLog
from core.utils import safe_audit_log
from core.exceptions import BusinessLogicError
from django.core.exceptions import ValidationError
from users.models import CustomUser
from notifications.services import NotificationService
from .models import CommissionLedger, FinancialAdjustment, ClientCredit

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# Importar el nuevo cliente
from .wompi_payouts_client import WompiPayoutsClient, WompiPayoutsError

# Mantener alias para compatibilidad
WompiPayoutError = WompiPayoutsError


class WompiDisbursementClient:
    """
    Cliente wrapper para mantener compatibilidad con código existente.

    Delega todas las operaciones al nuevo WompiPayoutsClient que implementa
    correctamente la API de Wompi Payouts.
    """

    def __init__(self):
        """Inicializa el cliente delegando al WompiPayoutsClient."""
        self._client = WompiPayoutsClient()

    def get_available_balance(self, account_id: Optional[str] = None) -> Decimal:
        """
        Obtiene el saldo disponible.

        Args:
            account_id: ID de cuenta específica (opcional)

        Returns:
            Saldo en COP
        """
        try:
            return self._client.get_available_balance(account_id=account_id)
        except WompiPayoutsError as exc:
            # Convertir a excepción legacy para compatibilidad
            raise WompiPayoutError(str(exc)) from exc

    def create_payout(self, amount: Decimal, reference: Optional[str] = None) -> str:
        """
        Crea una orden de pago al desarrollador.

        Args:
            amount: Monto a dispersar en COP
            reference: Referencia única (opcional, se genera si no se provee)

        Returns:
            ID del lote de pago creado
        """
        if not reference:
            # Generar referencia única si no se provee
            reference = f"DEV-COMM-{timezone.now().strftime('%Y%m%d-%H%M%S')}"

        try:
            payout_id, payout_data = self._client.create_payout(
                amount=amount,
                reference=reference,
                beneficiary_data=None,  # Usa datos del desarrollador por defecto
                account_id=None,  # Usa primera cuenta disponible
            )

            logger.info(
                "Payout creado para desarrollador: ID=%s, Monto=$%s, Estado=%s",
                payout_id,
                amount,
                payout_data.get("status", "unknown")
            )

            return payout_id

        except WompiPayoutsError as exc:
            # Convertir a excepción legacy para compatibilidad
            raise WompiPayoutError(str(exc)) from exc


class DeveloperCommissionService:
    """
    Orquesta el registro de comisiones, cálculo de deuda y pagos al desarrollador.
    """

    @classmethod
    @transaction.atomic
    def register_commission(cls, payment):
        if payment is None or payment.amount in (None, Decimal("0")):
            return None

        if CommissionLedger.objects.filter(source_payment=payment).exists():
            return None

        settings_obj = GlobalSettings.load()
        percentage = settings_obj.developer_commission_percentage
        if not percentage or percentage <= 0:
            return None

        amount = (
            _to_decimal(payment.amount)
            * _to_decimal(percentage)
            / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amount <= 0:
            return None

        return CommissionLedger.objects.create(
            amount=amount,
            source_payment=payment,
            status=CommissionLedger.Status.PENDING,
            payment_type=payment.payment_type or "",
            payment_method=payment.payment_method_type or "",
        )

    @staticmethod
    def get_developer_debt(include_failed: bool = True) -> Decimal:
        statuses = [CommissionLedger.Status.PENDING]
        if include_failed:
            statuses.append(CommissionLedger.Status.FAILED_NSF)
        aggregate = CommissionLedger.objects.filter(
            status__in=statuses
        ).aggregate(total=Coalesce(Sum(F("amount") - F("paid_amount")), Decimal("0")))
        total = aggregate["total"] or Decimal("0")
        return total.quantize(Decimal("0.01"))

    @classmethod
    def handle_successful_payment(cls, payment):
        ledger = cls.register_commission(payment)
        if not ledger:
            return None
        return cls.evaluate_payout()

    @classmethod
    def evaluate_payout(cls):
        settings_obj = GlobalSettings.load()
        debt = cls.get_developer_debt()
        if debt <= Decimal("0"):
            cls._exit_default(settings_obj)
            return {"status": "no_debt"}

        threshold = settings_obj.developer_payout_threshold
        if not settings_obj.developer_in_default and debt < threshold:
            return {"status": "below_threshold", "debt": str(debt)}

        return cls._attempt_payout(settings_obj, debt)

    @classmethod
    def _attempt_payout(cls, settings_obj, current_debt: Decimal):
        client = WompiDisbursementClient()
        try:
            balance = client.get_available_balance()
        except WompiPayoutError as exc:
            logger.error("No se pudo consultar saldo Wompi: %s", exc)
            cls._enter_default(settings_obj, current_debt=current_debt)
            cls._mark_failed_nsf()
            cls._log_payout_failure("balance_unavailable", detail=str(exc))
            return {"status": "balance_unavailable", "detail": str(exc)}

        amount_to_pay = min(current_debt, balance)
        if amount_to_pay <= Decimal("0"):
            cls._enter_default(settings_obj, current_debt=current_debt)
            cls._mark_failed_nsf()
            cls._log_payout_failure(
                "insufficient_funds",
                debt=str(current_debt),
                balance=str(balance),
            )
            return {"status": "insufficient_funds", "debt": str(current_debt), "balance": str(balance)}

        try:
            wompi_transfer_id = client.create_payout(amount_to_pay)
        except WompiPayoutError as exc:
            logger.error("Payout al desarrollador falló: %s", exc)
            cls._enter_default(settings_obj, current_debt=current_debt)
            cls._mark_failed_nsf()
            cls._log_payout_failure("payout_failed", detail=str(exc))
            return {"status": "payout_failed", "detail": str(exc)}

        cls._apply_payout_to_ledger(amount_to_pay, wompi_transfer_id)
        remaining_debt = cls.get_developer_debt()
        if remaining_debt <= Decimal("0"):
            cls._exit_default(settings_obj)
        else:
            cls._enter_default(settings_obj, current_debt=remaining_debt)
        return {"status": "paid", "amount": str(amount_to_pay), "remaining_debt": str(remaining_debt)}

    @classmethod
    @transaction.atomic
    def _apply_payout_to_ledger(cls, amount_to_pay: Decimal, transfer_id: str, performed_by=None):
        remaining = amount_to_pay
        entries = (
            CommissionLedger.objects.select_for_update()
            .filter(status__in=[CommissionLedger.Status.PENDING, CommissionLedger.Status.FAILED_NSF])
            .order_by("created_at")
        )
        now = timezone.now()
        paid_entries = []
        for entry in entries:
            if remaining <= Decimal("0"):
                break
            due = entry.pending_amount
            if due <= Decimal("0"):
                continue
            chunk = min(due, remaining)
            previous_status = entry.status
            entry.paid_amount = (entry.paid_amount or Decimal("0")) + chunk
            entry.wompi_transfer_id = transfer_id
            if entry.paid_amount >= entry.amount:
                entry.status = CommissionLedger.Status.PAID
                entry.paid_at = now
            entry.save(
                update_fields=[
                    "paid_amount",
                    "status",
                    "wompi_transfer_id",
                    "paid_at",
                    "updated_at",
                ]
            )
            paid_entries.append(entry)
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                admin_user=performed_by,
                details={
                    "action": "commission_payout_applied",
                    "ledger_id": str(entry.id),
                    "payment_id": str(entry.source_payment_id),
                    "amount_paid": str(chunk),
                    "previous_status": previous_status,
                    "new_status": entry.status,
                    "wompi_transfer_id": transfer_id,
                    "total_paid": str(entry.paid_amount),
                    "total_amount": str(entry.amount),
                },
            )
            remaining -= chunk
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=performed_by,
            details={
                "action": "developer_payout_completed",
                "total_amount": str(amount_to_pay),
                "wompi_transfer_id": transfer_id,
                "entries_paid": len(paid_entries),
                "timestamp": now.isoformat(),
            },
        )

    @staticmethod
    def _log_payout_failure(reason: str, **extra):
        details = {"action": "developer_payout_failed", "reason": reason}
        if extra:
            details.update(extra)
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            details=details,
        )

    @staticmethod
    def _enter_default(settings_obj, current_debt=None):
        if not settings_obj.developer_in_default:
            settings_obj.developer_in_default = True
            settings_obj.developer_default_since = timezone.now()
            settings_obj.save(update_fields=["developer_in_default", "developer_default_since", "updated_at"])
            
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details={
                    "action": "developer_default_entered",
                    "timestamp": timezone.now().isoformat(),
                    "debt": str(current_debt) if current_debt else "unknown",
                },
            )

            # Notificar a superusuarios
            admins = CustomUser.objects.filter(is_superuser=True)
            for admin in admins:
                try:
                    NotificationService.send_notification(
                        user=admin,
                        event_code="DEVELOPER_DEFAULT_ENTERED",
                        context={
                            "timestamp": timezone.now().isoformat(),
                            "debt": str(current_debt) if current_debt else "N/A",
                            "threshold": str(settings_obj.developer_payout_threshold),
                        },
                        priority="high"
                    )
                except Exception:
                    logger.exception("Failed to notify admin %s about developer default", admin.id)

    @staticmethod
    def _exit_default(settings_obj):
        if settings_obj.developer_in_default:
            settings_obj.developer_in_default = False
            settings_obj.developer_default_since = None
            settings_obj.save(update_fields=["developer_in_default", "developer_default_since", "updated_at"])
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                details={
                    "action": "developer_default_exited",
                    "timestamp": timezone.now().isoformat(),
                },
            )

    @classmethod
    @transaction.atomic
    def _mark_failed_nsf(cls):
        CommissionLedger.objects.select_for_update().filter(
            status=CommissionLedger.Status.PENDING
        ).update(
            status=CommissionLedger.Status.FAILED_NSF,
            updated_at=timezone.now(),
        )


class FinancialAdjustmentService:
    CREDIT_TTL_DAYS = 365
    MAX_MANUAL_ADJUSTMENT = Decimal("5000000")

    @classmethod
    @transaction.atomic
    def create_adjustment(cls, *, user, amount, adjustment_type, reason, created_by, related_payment=None):
        if amount <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")
        if Decimal(amount) > cls.MAX_MANUAL_ADJUSTMENT:
            raise BusinessLogicError(
                detail="El monto excede el límite permitido para ajustes manuales.",
                internal_code="PAY-ADJ-LIMIT",
            )
        adjustment = FinancialAdjustment.objects.create(
            user=user,
            amount=amount,
            adjustment_type=adjustment_type,
            reason=reason,
            related_payment=related_payment,
            created_by=created_by,
        )
        details_parts = [
            f"Tipo: {adjustment.get_adjustment_type_display()}",
            f"Monto: COP {Decimal(amount):,.2f}",
        ]
        if reason:
            details_parts.append(f"Razón: {reason}")
        if related_payment:
            details_parts.append(f"Pago relacionado: {related_payment.id}")
        AuditLog.objects.create(
            admin_user=created_by,
            target_user=user,
            action=AuditLog.Action.FINANCIAL_ADJUSTMENT_CREATED,
            details=" | ".join(details_parts),
        )
        if adjustment_type == FinancialAdjustment.AdjustmentType.CREDIT:
            expires = timezone.now().date() + timedelta(days=cls.CREDIT_TTL_DAYS)
            ClientCredit.objects.create(
                user=user,
                originating_payment=related_payment,
                initial_amount=amount,
                remaining_amount=amount,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires,
            )
        return adjustment


class CreditManagementService:
    """
    Servicio centralizado para la gestión de créditos (emisión y penalizaciones).
    """

    @classmethod
    @transaction.atomic
    def issue_credit_from_appointment(cls, *, appointment, percentage, created_by, reason):
        """
        Genera crédito a partir de los pagos de una cita (ej. reembolso por cancelación).
        """
        from finances.models import Payment, ClientCredit
        
        percentage = Decimal(str(percentage))
        if percentage <= 0:
            return Decimal('0'), []
            
        # Buscar pagos de anticipo aprobados
        payments = appointment.payments.select_for_update().filter(
            payment_type__in=[
                Payment.PaymentType.ADVANCE,
                Payment.PaymentType.FINAL,
            ],
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ],
        )
        
        if not payments.exists():
            return Decimal('0'), []

        settings_obj = GlobalSettings.load()
        expires_at = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
        total_created = Decimal('0')
        created_credits = []
        
        for payment in payments:
            if hasattr(payment, "generated_credit"):
                continue
                
            credit_amount = (payment.amount or Decimal('0')) * percentage
            if credit_amount <= 0:
                continue
                
            credit = ClientCredit.objects.create(
                user=appointment.user,
                originating_payment=payment,
                initial_amount=credit_amount,
                remaining_amount=credit_amount,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires_at,
            )
            total_created += credit_amount
            created_credits.append(credit)

        if total_created > 0:
            AuditLog.objects.create(
                admin_user=created_by,
                target_user=appointment.user,
                target_appointment=appointment,
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN, # O una acción más genérica de crédito
                details=reason or f"Crédito generado por cita {appointment.id}",
            )
            
        return total_created, created_credits

    @classmethod
    @transaction.atomic
    def apply_cancellation_penalty(cls, user, appointment, history):
        """
        Aplica penalización de 3 strikes: expira el crédito más antiguo.
        """
        if len(history) < 3:
            return

        # Reforzar atomicidad con lock sobre el usuario
        # Nota: Asumimos que 'user' ya es una instancia válida, pero recargamos con lock
        User = user.__class__
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        
        # Buscar el crédito objetivo (primero o último del historial)
        target_credit_id = history[0].get("credit_id")
        target_credit = cls._get_available_credit(target_credit_id)
        
        if not target_credit:
            target_credit_id = history[-1].get("credit_id")
            target_credit = cls._get_available_credit(target_credit_id)
            
        if target_credit:
            target_credit.status = ClientCredit.CreditStatus.EXPIRED
            target_credit.remaining_amount = Decimal('0')
            target_credit.save(update_fields=['status', 'remaining_amount', 'updated_at'])
            
        AuditLog.objects.create(
            admin_user=None,
            target_user=locked_user,
            target_appointment=appointment,
            action=AuditLog.Action.SYSTEM_CANCEL,
            details="Penalización por sabotaje de agenda (3 strikes).",
        )
        
        locked_user.cancellation_streak = []
        locked_user.save(update_fields=['cancellation_streak', 'updated_at'])

    @staticmethod
    def _get_available_credit(credit_id):
        if not credit_id:
            return None
        try:
            credit = ClientCredit.objects.select_for_update().get(id=credit_id)
        except ClientCredit.DoesNotExist:
            return None
            
        if credit.status not in [
            ClientCredit.CreditStatus.AVAILABLE,
            ClientCredit.CreditStatus.PARTIALLY_USED,
        ]:
            return None
        return credit
