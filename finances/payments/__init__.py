"""
Paquete de Servicios de Pago.

Este paquete fue refactorizado desde un único archivo payments.py (~1580 líneas)
para mejorar la mantenibilidad y organización del código.

Exporta:
- PaymentService: Clase principal que agrupa toda la funcionalidad
- CreditApplicationResult: Resultado de aplicar créditos

Módulos internos:
- credits: Lógica FIFO de créditos
- status_handler: Procesamiento de estado de gateway
- appointment_initiation: Flujo de inicio de pago de citas
- appointment_payments: Funciones base de pagos de citas
- order_payments: Pagos de órdenes y paquetes
- wompi_methods: Métodos de pago PSE/Nequi/Daviplata/Bancolombia
- recurrence: Cobros recurrentes
- utils: Utilidades varias
"""
from finances.payments.credits import (
    CreditApplicationResult,
    apply_credits_to_payment,
    preview_credits_application,
)
from finances.payments.status_handler import (
    apply_gateway_status,
    poll_pending_payment,
    send_payment_status_notification,
)
from finances.payments.appointment_initiation import initiate_appointment_payment
from finances.payments.appointment_payments import (
    calculate_outstanding_amount,
    create_tip_payment,
    create_final_payment,
    create_cash_advance_payment,
    AppointmentPaymentHelper,
)
from finances.payments.order_payments import (
    create_package_payment,
    create_order_payment,
)
from finances.payments.wompi_methods import (
    create_pse_payment,
    create_nequi_payment,
    create_daviplata_payment,
    create_bancolombia_transfer_payment,
)
from finances.payments.recurrence import charge_recurrence_token
from finances.payments.utils import (
    build_tax_payload,
    build_customer_data,
    describe_payment_service,
    extract_decline_reason,
    reset_user_cancellation_history,
    generate_checkout_url,
    cancel_pending_payments_for_appointment,
)
from finances.gateway import WompiPaymentClient


class PaymentService:
    """
    Servicio para manejar la lógica de negocio de los pagos,
    incluyendo la aplicación de saldo a favor (ClientCredit).
    
    Esta clase actúa como fachada que delega a los módulos especializados.
    Mantiene compatibilidad con el código existente.
    """
    WOMPI_DEFAULT_BASE_URL = "https://production.wompi.co/v1"

    def __init__(self, user):
        self.user = user
        self._helper = AppointmentPaymentHelper(user)

    # ========================================
    # CRÉDITOS
    # ========================================
    
    @staticmethod
    def apply_credits_to_payment(user, total_amount):
        """Aplica créditos disponibles del usuario a un monto total (FIFO)."""
        return apply_credits_to_payment(user, total_amount)
    
    @staticmethod
    def preview_credits_application(user, total_amount):
        """Preview de créditos sin modificar la base de datos."""
        return preview_credits_application(user, total_amount)

    # ========================================
    # ESTADO DE GATEWAY
    # ========================================
    
    @staticmethod
    def apply_gateway_status(payment, gateway_status, transaction_payload=None):
        """Procesa estado recibido de Wompi y ejecuta side-effects."""
        return apply_gateway_status(payment, gateway_status, transaction_payload)
    
    @staticmethod
    def poll_pending_payment(payment, timeout_minutes=30):
        """Consulta estado de un pago pendiente en Wompi."""
        return poll_pending_payment(payment, timeout_minutes)

    # ========================================
    # PAGOS DE CITAS
    # ========================================
    
    @staticmethod
    def initiate_appointment_payment(
        appointment,
        user,
        payment_type: str = 'deposit',
        use_credits: bool = False,
        confirm: bool = False
    ):
        """Inicia el flujo de pago para una cita (preview o confirmación)."""
        return initiate_appointment_payment(
            appointment=appointment,
            user=user,
            payment_type=payment_type,
            use_credits=use_credits,
            confirm=confirm
        )
    
    @staticmethod
    def calculate_outstanding_amount(appointment):
        """Calcula el saldo pendiente de una cita."""
        return calculate_outstanding_amount(appointment)
    
    @staticmethod
    def create_tip_payment(appointment, user, amount):
        """Crea un pago de propina para una cita completada."""
        return create_tip_payment(appointment, user, amount)
    
    @staticmethod
    def create_final_payment(appointment, user):
        """Crea pago final para completar el saldo de una cita."""
        return create_final_payment(appointment, user)
    
    @staticmethod
    def create_cash_advance_payment(appointment, amount, notes=""):
        """Crea un registro de pago en efectivo recibido en persona."""
        return create_cash_advance_payment(appointment, amount, notes)

    def create_advance_payment_for_appointment(self, appointment):
        """Crea el registro de pago de anticipo para una cita."""
        return self._helper.create_advance_payment_for_appointment(appointment)

    # ========================================
    # PAGOS DE ÓRDENES Y PAQUETES
    # ========================================
    
    @staticmethod
    def create_package_payment(user, package):
        """Crea un registro de pago para la compra de un paquete."""
        return create_package_payment(user, package)
    
    @staticmethod
    def create_order_payment(user, order, use_credits=False):
        """Crea o actualiza un registro de pago para una orden de marketplace."""
        return create_order_payment(user, order, use_credits)

    # ========================================
    # MÉTODOS DE PAGO WOMPI
    # ========================================
    
    @classmethod
    def create_pse_payment(
        cls,
        *,
        payment,
        user_type: int,
        user_legal_id: str,
        user_legal_id_type: str,
        financial_institution_code: str,
        payment_description: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción PSE en Wompi."""
        return create_pse_payment(
            payment=payment,
            user_type=user_type,
            user_legal_id=user_legal_id,
            user_legal_id_type=user_legal_id_type,
            financial_institution_code=financial_institution_code,
            payment_description=payment_description,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )
    
    @classmethod
    def create_nequi_payment(
        cls,
        *,
        payment,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción Nequi en Wompi."""
        return create_nequi_payment(
            payment=payment,
            phone_number=phone_number,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )
    
    @classmethod
    def create_daviplata_payment(
        cls,
        *,
        payment,
        phone_number: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción Daviplata en Wompi."""
        return create_daviplata_payment(
            payment=payment,
            phone_number=phone_number,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )
    
    @classmethod
    def create_bancolombia_transfer_payment(
        cls,
        *,
        payment,
        payment_description: str,
        redirect_url: str | None = None,
        expiration_time: str | None = None,
    ):
        """Crea una transacción Bancolombia Transfer en Wompi."""
        return create_bancolombia_transfer_payment(
            payment=payment,
            payment_description=payment_description,
            redirect_url=redirect_url,
            expiration_time=expiration_time,
        )

    # ========================================
    # COBROS RECURRENTES
    # ========================================
    
    @classmethod
    def charge_recurrence_token(cls, user, amount, token):
        """Ejecuta un cobro recurrente usando payment_source_id."""
        return charge_recurrence_token(user, amount, token)

    # ========================================
    # UTILIDADES
    # ========================================
    
    @staticmethod
    def _build_tax_payload(payment):
        """Construye tax_in_cents para Wompi."""
        return build_tax_payload(payment)
    
    @staticmethod
    def _build_customer_data(payment):
        """Construye customer_data para Wompi."""
        return build_customer_data(payment)
    
    @staticmethod
    def _describe_payment_service(payment):
        """Genera descripción legible del servicio asociado al pago."""
        return describe_payment_service(payment)
    
    @staticmethod
    def _extract_decline_reason(transaction_payload):
        """Extrae razón de rechazo del payload de Wompi."""
        return extract_decline_reason(transaction_payload)
    
    @staticmethod
    def reset_user_cancellation_history(appointment):
        """Resetea el historial de cancelaciones del usuario."""
        return reset_user_cancellation_history(appointment)
    
    @staticmethod
    def generate_checkout_url(payment):
        """Genera una URL de checkout hosted de Wompi."""
        return generate_checkout_url(payment)
    
    @staticmethod
    def cancel_pending_payments_for_appointment(appointment):
        """Cancela todos los pagos pendientes de una cita cancelada."""
        return cancel_pending_payments_for_appointment(appointment)
    
    @classmethod
    def _resolve_acceptance_token(cls, base_url=None):
        """Resuelve el token de aceptación de Wompi."""
        return WompiPaymentClient.resolve_acceptance_token(base_url=base_url)
    
    @staticmethod
    def _send_payment_status_notification(*, payment, new_status, previous_status, transaction_payload):
        """Envía notificación de estado de pago al usuario."""
        return send_payment_status_notification(
            payment=payment,
            new_status=new_status,
            previous_status=previous_status,
            transaction_payload=transaction_payload
        )


# Exportar para compatibilidad con imports existentes
__all__ = [
    'PaymentService',
    'CreditApplicationResult',
]
