"""
Tests para verificar que los pagos pendientes se cancelan correctamente
cuando se cancela una cita, evitando bloqueo por deuda.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from spa.models import Appointment, Service, ServiceCategory
from finances.models import Payment
from finances.payments import PaymentService
from users.models import CustomUser
from spa.services import AppointmentService

User = get_user_model()


class CancelPaymentOnCancelAppointmentTestCase(TestCase):
    """
    Tests que verifican que al cancelar una cita, los pagos pendientes
    se cancelan automáticamente para evitar bloqueo por deuda.
    """

    def setUp(self):
        """Create test data."""
        self.client_user = User.objects.create_user(
            email='client_debt@test.com',
            phone_number='+573005555555',
            password='testpass123',
            role=CustomUser.Role.CLIENT,
            first_name='Test',
            last_name='DebtClient'
        )

        self.staff_user = User.objects.create_user(
            email='staff_debt@test.com',
            phone_number='+573006666666',
            password='testpass123',
            role=CustomUser.Role.STAFF,
            first_name='Staff',
            last_name='Test'
        )

        category = ServiceCategory.objects.create(name='Test Category Debt')
        self.service = Service.objects.create(
            name='Test Service Debt',
            description='Test',
            duration=60,
            price=100000,
            category=category
        )

    def test_pending_payment_cancelled_when_appointment_cancelled(self):
        """
        Cuando se cancela una cita con pago pendiente,
        el pago debe cambiar a estado CANCELLED.
        """
        # Crear cita con pago pendiente
        appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.PENDING_PAYMENT,
            price_at_purchase=100000,
        )

        # Crear pago pendiente (anticipo)
        payment = Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ADVANCE,
        )

        # Verificar estado inicial
        self.assertEqual(payment.status, Payment.PaymentStatus.PENDING)
        self.assertEqual(appointment.status, Appointment.AppointmentStatus.PENDING_PAYMENT)

        # Cancelar la cita
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.save()

        # Llamar al método que cancela pagos pendientes
        PaymentService.cancel_pending_payments_for_appointment(appointment)

        # Refrescar el pago de la BD
        payment.refresh_from_db()

        # Verificar que el pago fue cancelado
        self.assertEqual(payment.status, Payment.PaymentStatus.CANCELLED)

    def test_multiple_pending_payments_cancelled(self):
        """
        Si hay múltiples pagos pendientes (anticipo + final),
        todos deben ser cancelados.
        """
        appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100000,
        )

        # Crear múltiples pagos pendientes
        payment_advance = Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ADVANCE,
        )

        payment_final = Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        )

        # Cancelar la cita y pagos
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.save()
        count = PaymentService.cancel_pending_payments_for_appointment(appointment)

        # Verificar que se cancelaron 2 pagos
        self.assertEqual(count, 2)

        # Verificar que ambos pagos están cancelados
        payment_advance.refresh_from_db()
        payment_final.refresh_from_db()
        self.assertEqual(payment_advance.status, Payment.PaymentStatus.CANCELLED)
        self.assertEqual(payment_final.status, Payment.PaymentStatus.CANCELLED)

    def test_approved_payments_not_cancelled(self):
        """
        Los pagos ya aprobados NO deben ser cancelados,
        solo los que están en estado PENDING.
        """
        appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100000,
        )

        # Pago aprobado (ya se pagó el anticipo)
        payment_approved = Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.APPROVED,
            payment_type=Payment.PaymentType.ADVANCE,
        )

        # Pago pendiente (pago final)
        payment_pending = Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        )

        # Cancelar la cita
        appointment.status = Appointment.AppointmentStatus.CANCELLED
        appointment.save()
        count = PaymentService.cancel_pending_payments_for_appointment(appointment)

        # Solo 1 pago debe haber sido cancelado
        self.assertEqual(count, 1)

        # El pago aprobado debe permanecer aprobado
        payment_approved.refresh_from_db()
        self.assertEqual(payment_approved.status, Payment.PaymentStatus.APPROVED)

        # El pago pendiente debe estar cancelado
        payment_pending.refresh_from_db()
        self.assertEqual(payment_pending.status, Payment.PaymentStatus.CANCELLED)

    def test_user_not_blocked_after_cancelling_appointment_with_pending_payment(self):
        """
        CASO CRÍTICO: Un usuario con una cita cancelada que tenía pago pendiente
        NO debe quedar bloqueado para crear nuevas citas.
        """
        # Crear cita con pago pendiente
        appointment1 = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.PENDING_PAYMENT,
            price_at_purchase=100000,
        )

        payment1 = Payment.objects.create(
            user=self.client_user,
            appointment=appointment1,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ADVANCE,
        )

        # Cancelar la cita
        appointment1.status = Appointment.AppointmentStatus.CANCELLED
        appointment1.save()
        PaymentService.cancel_pending_payments_for_appointment(appointment1)

        # Intentar crear una nueva cita - NO debe estar bloqueado
        service_obj = AppointmentService(
            user=self.client_user,
            services=[self.service],
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=3),
        )

        # Esto NO debe lanzar BusinessLogicError de "Usuario bloqueado por deuda"
        try:
            new_appointment = service_obj.create_appointment_with_lock()
            self.assertIsNotNone(new_appointment)
            self.assertEqual(new_appointment.user, self.client_user)
        except Exception as e:
            self.fail(f"Usuario no debería estar bloqueado después de cancelar cita, pero obtuvo: {str(e)}")

    def test_user_blocked_with_pending_final_payment_active_appointment(self):
        """
        CASO DE CONTROL: Un usuario con pago final pendiente de una cita ACTIVA
        SÍ debe quedar bloqueado.
        """
        # Crear cita confirmada con pago final pendiente
        appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,  # Activa
            price_at_purchase=100000,
        )

        # Pago aprobado (anticipo)
        Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.APPROVED,
            payment_type=Payment.PaymentType.ADVANCE,
        )

        # Pago pendiente (pago final)
        Payment.objects.create(
            user=self.client_user,
            appointment=appointment,
            amount=Decimal('50000'),
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        )

        # Intentar crear nueva cita - DEBE estar bloqueado
        from core.utils.exceptions import BusinessLogicError

        service_obj = AppointmentService(
            user=self.client_user,
            services=[self.service],
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=3),
        )

        with self.assertRaises(BusinessLogicError) as context:
            service_obj.create_appointment_with_lock()

        self.assertIn("bloqueado por deuda", str(context.exception.detail).lower())

    def test_no_payments_to_cancel_returns_zero(self):
        """
        Si no hay pagos pendientes, debe retornar 0.
        """
        appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100000,
        )

        # Sin pagos pendientes
        count = PaymentService.cancel_pending_payments_for_appointment(appointment)
        self.assertEqual(count, 0)
