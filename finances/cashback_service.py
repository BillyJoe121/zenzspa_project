import logging
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from core.models import GlobalSettings, AuditLog
from finances.models import Payment, ClientCredit, PaymentCreditUsage
from users.models import CustomUser

logger = logging.getLogger(__name__)

class CashbackService:
    """
    Servicio para gestionar el cashback de usuarios VIP.
    """

    @classmethod
    @transaction.atomic
    def process_cashback(cls, payment: Payment):
        """
        Procesa y genera cashback si corresponde para un pago aprobado.
        
        Reglas:
        - El pago debe estar APROBADO.
        - El usuario debe ser VIP.
        - El porcentaje de cashback global debe ser > 0.
        - No se genera cashback sobre montos pagados con créditos.
        - Se evitan duplicados verificando si ya existe cashback para este pago.
        
        Args:
            payment (Payment): El pago aprobado.
            
        Returns:
            ClientCredit or None: El crédito generado o None si no aplica.
        """
        if not payment or not payment.user:
            return None
            
        if not payment.is_approved:
            logger.warning("Intento de cashback en pago no aprobado: %s", payment.id)
            return None

        # Verificar si ya existe cashback generado por este pago
        if ClientCredit.objects.filter(
            originating_payment=payment, 
        ).filter(initial_amount__gt=0).exists():
            logger.info("Cashback omitido: ya existe crédito para pago %s", payment.id)
            return None
            
        # Verificar estado VIP
        if payment.user.role != CustomUser.Role.VIP:
            return None
            
        settings_obj = GlobalSettings.load()
        cashback_percentage = settings_obj.vip_cashback_percentage
        
        if not cashback_percentage or cashback_percentage <= 0:
            return None
            
        # Calcular monto base para cashback
        # Payment.amount es el monto total de la transacción 'externa' (Wompi) usualmente.
        # Pero si el sistema permite pagos mixtos donde Payment engloba todo, debemos restar credit_usages.
        # Basado en PaymentCreditUsage, parece que los créditos se linkean al Payment.
        # Si payment.amount incluye el crédito, debemos restarlo.
        # Si payment.amount es SOLO lo cobrado en gateway, entonces es la base correcta.
        
        # Asumiremos la interpretación más segura: EL CASHBACK ES SOBRE DINERO REAL PAGADO.
        # Si Payment.amount representa el 'Total a Pagar' (incluyendo créditos), restamos créditos.
        # Si Payment.amount representa 'Monto Transaccionado' (Gateway), usamos ese directo.
        
        # En Webhooks de Wompi, el payment.amount se valida contra 'amount_in_cents' de Wompi.
        # Por tanto, Payment.amount == Dinero Real cobrado por Wompi.
        # LOS CRÉDITOS NO PASAN POR WOMPI.
        # Entonces, Payment.amount es la base correcta (Neto Cash).
        
        base_amount = payment.amount
        
        if base_amount <= 0:
            return None
            
        # Calcular cashback
        cashback_amount = (base_amount * (cashback_percentage / Decimal('100'))).quantize(Decimal('0.01'))
        
        if cashback_amount <= 0:
            return None
            
        # Configurar expiración (usamos la misma que créditos normales por ahora, o 30 días si se prefiere)
        expires_at = timezone.now().date() + timedelta(days=settings_obj.credit_expiration_days)
        
        # Crear Crédito
        credit = ClientCredit.objects.create(
            user=payment.user,
            originating_payment=payment, # Link clave para reversión
            initial_amount=cashback_amount,
            remaining_amount=cashback_amount,
            status=ClientCredit.CreditStatus.AVAILABLE,
            expires_at=expires_at
        )
        
        logger.info(
            "Cashback VIP generado: User=%s, Payment=%s, Base=%s, Pct=%s%%, Amount=%s",
            payment.user.id, payment.id, base_amount, cashback_percentage, cashback_amount
        )
        
        return credit

    @classmethod
    @transaction.atomic
    def revert_cashback(cls, source_object):
        """
        Revierte el cashback asociado a una orden o cita cancelada.
        
        Args:
            source_object: Instance de Order o Appointment que se está cancelando.
        """
        # Encontrar los pagos asociados a este objeto
        payments = []
        if hasattr(source_object, 'payments'):
            payments = source_object.payments.all()
            
        if not payments:
            return

        reverted_total = Decimal('0')
        
        for payment in payments:
            # Buscar créditos generados por este pago
            # Asumimos que CUALQUIER crédito generado por este pago es un cashback o refund automático.
            # Al cancelar la orden/cita, tiene sentido anular ambos si el refund original también se anula (caso raro).
            # Pero para cashback, esto es lo que queremos.
            credits = ClientCredit.objects.filter(
                originating_payment=payment,
                status__in=[
                    ClientCredit.CreditStatus.AVAILABLE,
                    ClientCredit.CreditStatus.PARTIALLY_USED,
                    ClientCredit.CreditStatus.USED
                ]
            )
            
            for credit in credits:
                # Calcular cuánto debemos revertir
                # Si el crédito ya fue usado, el saldo del usuario se volverá negativo (si permitimos deuda)
                # o el crédito queda en 0 y logueamos la "deuda".
                
                # Vamos a marcarlo como CANCELLED/EXPIRED y restar el saldo.
                # Como ClientCredit no tiene soporte nativo para "saldos negativos" en una cuenta corriente global,
                # sino que son bolsas individuales...
                
                # Estrategia:
                # 1. Si está AVAILABLE (intacto o parcial), lo anulamos.
                # 2. Si está USED o PARTIALLY, significa que el usuario ya gastó ese dinero "regalado".
                #    Tenemos dos opciones:
                #    A) Crear un "Débito" (FinancialAdjustment) para compensar.
                #    B) Anular el crédito usado (no afecta nada histórico) y crear una deuda.
                
                # Implementación simple: Anular lo que queda y registrar Log.
                # La regla de negocio dice: "cashback... será eliminado".
                
                remanente = credit.remaining_amount
                usado = credit.initial_amount - remanente
                
                # Anular remanente
                credit.remaining_amount = Decimal('0')
                credit.status = ClientCredit.CreditStatus.EXPIRED # O un status nuevo REVOKED
                credit.save()
                
                if usado > 0:
                    # El usuario gastó dinero que ahora estamos revocando.
                    # Crear un ajuste negativo (Débito)
                    from finances.models import FinancialAdjustment
                    FinancialAdjustment.objects.create(
                        user=credit.user,
                        amount=usado,
                        adjustment_type=FinancialAdjustment.AdjustmentType.DEBIT,
                        reason=f"Reversión de cashback gastado por cancelación (Origen: {source_object})",
                        related_payment=payment,
                        created_by=None # Sistema
                    )
                    logger.warning(
                        "Cashback revertido pero ya estaba gastado. Se creó débito. Credit=%s, Usado=%s",
                        credit.id, usado
                    )
                
                reverted_total += credit.initial_amount

        if reverted_total > 0:
            logger.info("Cashback revertido para %s: Total %s", source_object, reverted_total)
