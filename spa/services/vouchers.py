import logging
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import AuditLog
from finances.models import Payment
from finances.subscriptions import VipMembershipService
from ..models import (
    Appointment,
    Package,
    UserPackage,
    Voucher,
)

logger = logging.getLogger(__name__)


class PackagePurchaseService:
    """
    Servicio para manejar la lógica de negocio de la compra de paquetes.
    """
    @staticmethod
    @transaction.atomic
    def fulfill_purchase(payment: Payment):
        """
        Crea el UserPackage y los Vouchers asociados después de un pago exitoso.
        Este método es idempotente; no hará nada si el paquete ya fue otorgado.

        Args:
            payment (Payment): La instancia del pago aprobado.
        """
        reference = payment.transaction_id or ""
        if not reference.startswith("PACKAGE-"):
            return
        raw_identifier = reference[len("PACKAGE-"):]
        package_id = raw_identifier.rsplit('-', 1)[0]
        try:
            package = Package.objects.get(id=package_id)
        except Package.DoesNotExist:
            return

        # Verificar si este pago ya procesó una compra para evitar duplicados.
        if hasattr(payment, 'user_package_purchase'):
            return

        # 1. Crear el registro de la compra (UserPackage)
        user_package = UserPackage.objects.create(
            user=payment.user,
            package=package,
            payment=payment
            # La fecha de expiración se calcula automáticamente en el método save() del modelo.
        )

        # 2. Generar los vouchers para cada servicio en el paquete
        # Usamos `packageservice_set` que definimos en el related_name a través de la tabla intermedia.
        for package_service in package.packageservice_set.all():
            for _ in range(package_service.quantity):
                Voucher.objects.create(
                    user_package=user_package,
                    user=payment.user,
                    service=package_service.service
                )

        if package.grants_vip_months:
            VipMembershipService.extend_membership(
                payment.user, package.grants_vip_months)

        return user_package


class VoucherRedemptionService:
    """
    Redime vouchers de forma atómica para evitar uso concurrente.
    """

    @staticmethod
    @transaction.atomic
    def redeem_voucher(voucher_code, user, appointment):
        try:
            voucher = Voucher.objects.select_for_update().get(
                code=voucher_code,
                status=Voucher.VoucherStatus.AVAILABLE,
                is_deleted=False,
            )
        except Voucher.DoesNotExist:
            raise BusinessLogicError(
                detail="Voucher no encontrado o inactivo.",
                internal_code="SPA-VOUCHER-INVALID",
            )

        if voucher.expires_at and voucher.expires_at < timezone.now().date():
            raise BusinessLogicError(
                detail="El voucher ha expirado.",
                internal_code="SPA-VOUCHER-EXPIRED",
            )

        if voucher.usage_history.filter(appointment=appointment).exists():  # type: ignore[attr-defined]
            raise BusinessLogicError(
                detail="Ya usaste este voucher en esta cita.",
                internal_code="SPA-VOUCHER-ALREADY-USED",
            )

        voucher.status = Voucher.VoucherStatus.USED
        voucher.save(update_fields=["status", "updated_at"])

        appointment.voucher = voucher  # type: ignore[attr-defined]
        appointment.save(update_fields=["voucher", "updated_at"])  # type: ignore[attr-defined]

        AuditLog.objects.create(
            admin_user=None,
            target_user=user,
            target_appointment=appointment,
            action=AuditLog.Action.VOUCHER_REDEEMED,
            details={"voucher_code": voucher_code},
        )
        return voucher


