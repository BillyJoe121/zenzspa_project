from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models import GlobalSettings, AuditLog
from core.utils.exceptions import BusinessLogicError
from finances.models import FinancialAdjustment, ClientCredit


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
        from finances.models import Payment, ClientCredit

        percentage = Decimal(str(percentage))
        if percentage <= 0:
            return Decimal("0"), []

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
            return Decimal("0"), []

        settings_obj = GlobalSettings.load()
        expires_at = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
        total_created = Decimal("0")
        created_credits = []

        for payment in payments:
            if hasattr(payment, "generated_credit"):
                continue

            credit_amount = (payment.amount or Decimal("0")) * percentage
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
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
                details=reason or f"Crédito generado por cita {appointment.id}",
            )

        return total_created, created_credits

    @classmethod
    @transaction.atomic
    def apply_cancellation_penalty(cls, user, appointment, history):
        if len(history) < 3:
            return

        User = user.__class__
        locked_user = User.objects.select_for_update().get(pk=user.pk)

        target_credit_id = history[0].get("credit_id")
        target_credit = cls._get_available_credit(target_credit_id)

        if not target_credit:
            target_credit_id = history[-1].get("credit_id")
            target_credit = cls._get_available_credit(target_credit_id)

        if target_credit:
            target_credit.status = ClientCredit.CreditStatus.EXPIRED
            target_credit.remaining_amount = Decimal("0")
            target_credit.save(update_fields=["status", "remaining_amount", "updated_at"])

        AuditLog.objects.create(
            admin_user=None,
            target_user=locked_user,
            target_appointment=appointment,
            action=AuditLog.Action.SYSTEM_CANCEL,
            details="Penalización por sabotaje de agenda (3 strikes).",
        )

        locked_user.cancellation_streak = []
        locked_user.save(update_fields=["cancellation_streak", "updated_at"])

    @classmethod
    @transaction.atomic
    def issue_credit_from_order(cls, *, order, created_by=None, reason=None):
        from finances.models import Payment, ClientCredit

        payments = Payment.objects.select_for_update().filter(
            order=order,
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ],
        )

        if not payments.exists():
            return Decimal("0"), []

        settings_obj = GlobalSettings.load()
        expires_at = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
        total_created = Decimal("0")
        created_credits = []

        for payment in payments:
            if ClientCredit.objects.filter(originating_payment=payment).exists():
                continue

            credit_amount = payment.amount or Decimal("0")
            if credit_amount <= 0:
                continue

            credit = ClientCredit.objects.create(
                user=order.user,
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
                target_user=order.user,
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
                details=reason or f"Crédito generado por cancelación de orden {order.id}",
            )

        return total_created, created_credits

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
