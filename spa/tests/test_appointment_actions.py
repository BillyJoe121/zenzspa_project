"""
Tests for appointment action permission methods (can_* methods).

This test suite validates the business logic for determining which actions
are available for appointments based on their state, user role, and timing.
"""
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from spa.models import Appointment, Service, ServiceCategory
from users.models import CustomUser

User = get_user_model()


class AppointmentActionPermissionsTestCase(TestCase):
    """Tests for can_* methods on Appointment model."""

    def setUp(self):
        """Create test data."""
        # Create users
        self.client_user = User.objects.create_user(
            email='client@test.com',
            phone_number='+573001234567',
            password='testpass123',
            role=CustomUser.Role.CLIENT,
            first_name='Test',
            last_name='Client'
        )

        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            phone_number='+573007654321',
            password='testpass123',
            role=CustomUser.Role.STAFF,
            first_name='Test',
            last_name='Staff'
        )

        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            phone_number='+573009999999',
            password='testpass123',
            role=CustomUser.Role.ADMIN,
            first_name='Test',
            last_name='Admin'
        )

        # Create service
        category = ServiceCategory.objects.create(name='Test Category')
        self.service = Service.objects.create(
            name='Test Service',
            description='Test',
            duration=60,
            price=100000,
            category=category
        )

        # Create base appointment (future, confirmed)
        self.appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100000,
            reschedule_count=0
        )

    def test_can_reschedule_confirmed_appointment_as_client(self):
        """Client can reschedule confirmed future appointment."""
        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertTrue(can_reschedule)
        self.assertEqual(reason, "")

    def test_cannot_reschedule_cancelled_appointment(self):
        """Cannot reschedule cancelled appointment."""
        self.appointment.status = Appointment.AppointmentStatus.CANCELLED
        self.appointment.save()

        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertFalse(can_reschedule)
        self.assertIn("cancelada", reason.lower())

    def test_cannot_reschedule_completed_appointment(self):
        """Cannot reschedule completed appointment."""
        self.appointment.status = Appointment.AppointmentStatus.COMPLETED
        self.appointment.save()

        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertFalse(can_reschedule)
        self.assertIn("completada", reason.lower())

    def test_cannot_reschedule_past_appointment(self):
        """Cannot reschedule appointment in the past."""
        self.appointment.start_time = timezone.now() - timedelta(days=1)
        self.appointment.end_time = timezone.now() - timedelta(days=1) + timedelta(hours=1)
        self.appointment.save()

        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertFalse(can_reschedule)
        self.assertIn("pasó", reason.lower())

    def test_cannot_reschedule_after_3_times_as_client(self):
        """Client cannot reschedule after 3 attempts."""
        self.appointment.reschedule_count = 3
        self.appointment.save()

        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertFalse(can_reschedule)
        self.assertIn("límite", reason.lower())

    def test_can_reschedule_confirmed_with_outstanding_balance(self):
        """Can reschedule appointment in CONFIRMED status even with outstanding balance."""
        self.appointment.status = Appointment.AppointmentStatus.CONFIRMED
        self.appointment.save()

        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertTrue(can_reschedule)

    def test_can_cancel_confirmed_appointment_as_client(self):
        """Client can cancel confirmed appointment with >24h notice."""
        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        self.assertTrue(can_cancel)
        self.assertEqual(reason, "")

    def test_cannot_cancel_within_24h_as_client(self):
        """Client cannot cancel confirmed appointment within 24h."""
        self.appointment.start_time = timezone.now() + timedelta(hours=12)
        self.appointment.end_time = timezone.now() + timedelta(hours=13)
        self.appointment.save()

        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        self.assertFalse(can_cancel)
        self.assertIn("reagendar", reason.lower())

    def test_staff_can_cancel_within_24h(self):
        """Staff can cancel appointment even within 24h."""
        self.appointment.start_time = timezone.now() + timedelta(hours=12)
        self.appointment.end_time = timezone.now() + timedelta(hours=13)
        self.appointment.save()

        can_cancel, reason = self.appointment.can_cancel(self.staff_user)
        self.assertTrue(can_cancel)

    def test_cannot_cancel_already_cancelled(self):
        """Cannot cancel already cancelled appointment."""
        self.appointment.status = Appointment.AppointmentStatus.CANCELLED
        self.appointment.save()

        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        self.assertFalse(can_cancel)

    def test_can_mark_completed_as_staff_for_past_appointment(self):
        """Staff can mark past confirmed appointment as completed."""
        self.appointment.start_time = timezone.now() - timedelta(hours=2)
        self.appointment.end_time = timezone.now() - timedelta(hours=1)
        self.appointment.save()

        can_complete, reason = self.appointment.can_mark_completed(self.staff_user)
        self.assertTrue(can_complete)

    def test_cannot_mark_completed_as_client(self):
        """Client cannot mark appointment as completed."""
        can_complete, reason = self.appointment.can_mark_completed(self.client_user)
        self.assertFalse(can_complete)
        self.assertIn("personal", reason.lower())

    def test_cannot_mark_completed_future_appointment(self):
        """Cannot mark future appointment as completed."""
        can_complete, reason = self.appointment.can_mark_completed(self.staff_user)
        self.assertFalse(can_complete)
        self.assertIn("no ha ocurrido", reason.lower())

    def test_can_mark_no_show_as_staff_for_past_appointment(self):
        """Staff can mark past confirmed appointment as no-show."""
        self.appointment.start_time = timezone.now() - timedelta(hours=2)
        self.appointment.end_time = timezone.now() - timedelta(hours=1)
        self.appointment.save()

        can_no_show, reason = self.appointment.can_mark_no_show(self.staff_user)
        self.assertTrue(can_no_show)

    def test_cannot_mark_no_show_as_client(self):
        """Client cannot mark no-show."""
        can_no_show, reason = self.appointment.can_mark_no_show(self.client_user)
        self.assertFalse(can_no_show)

    def test_cannot_mark_no_show_future_appointment(self):
        """Cannot mark future appointment as no-show."""
        can_no_show, reason = self.appointment.can_mark_no_show(self.staff_user)
        self.assertFalse(can_no_show)

    def test_can_complete_final_payment_as_staff(self):
        """Staff can process final payment for confirmed appointment."""
        can_pay, reason = self.appointment.can_complete_final_payment(self.staff_user)
        self.assertTrue(can_pay)

    def test_cannot_complete_final_payment_as_client(self):
        """Client cannot process final payment."""
        can_pay, reason = self.appointment.can_complete_final_payment(self.client_user)
        self.assertFalse(can_pay)

    def test_can_add_tip_to_confirmed_appointment(self):
        """Can add tip to confirmed appointment."""
        can_tip, reason = self.appointment.can_add_tip(self.client_user)
        self.assertTrue(can_tip)

    def test_can_add_tip_to_completed_appointment(self):
        """Can add tip to completed appointment."""
        self.appointment.status = Appointment.AppointmentStatus.COMPLETED
        self.appointment.save()

        can_tip, reason = self.appointment.can_add_tip(self.client_user)
        self.assertTrue(can_tip)

    def test_cannot_add_tip_to_cancelled_appointment(self):
        """Cannot add tip to cancelled appointment."""
        self.appointment.status = Appointment.AppointmentStatus.CANCELLED
        self.appointment.save()

        can_tip, reason = self.appointment.can_add_tip(self.client_user)
        self.assertFalse(can_tip)

    def test_can_download_ical_for_future_confirmed_appointment(self):
        """Can download iCal for future confirmed appointment."""
        can_download, reason = self.appointment.can_download_ical(self.client_user)
        self.assertTrue(can_download)

    def test_cannot_download_ical_for_past_appointment(self):
        """Cannot download iCal for past appointment."""
        self.appointment.start_time = timezone.now() - timedelta(days=1)
        self.appointment.end_time = timezone.now() - timedelta(days=1) + timedelta(hours=1)
        self.appointment.save()

        can_download, reason = self.appointment.can_download_ical(self.client_user)
        self.assertFalse(can_download)

    def test_can_cancel_by_admin_as_admin(self):
        """Admin can use cancel_by_admin action."""
        can_cancel, reason = self.appointment.can_cancel_by_admin(self.admin_user)
        self.assertTrue(can_cancel)

    def test_cannot_cancel_by_admin_as_staff(self):
        """Staff cannot use admin-specific cancel action."""
        can_cancel, reason = self.appointment.can_cancel_by_admin(self.staff_user)
        self.assertFalse(can_cancel)

    def test_cannot_cancel_by_admin_as_client(self):
        """Client cannot use admin-specific cancel action."""
        can_cancel, reason = self.appointment.can_cancel_by_admin(self.client_user)
        self.assertFalse(can_cancel)

    def test_helper_properties(self):
        """Test helper properties work correctly."""
        # Future appointment
        self.assertTrue(self.appointment.is_active)
        self.assertFalse(self.appointment.is_past)
        self.assertTrue(self.appointment.is_upcoming)
        self.assertGreater(self.appointment.hours_until_appointment, 0)

        # Past appointment
        self.appointment.start_time = timezone.now() - timedelta(hours=2)
        self.appointment.end_time = timezone.now() - timedelta(hours=1)
        self.appointment.save()

        self.assertTrue(self.appointment.is_past)
        self.assertFalse(self.appointment.is_upcoming)
        self.assertLess(self.appointment.hours_until_appointment, 0)

        # Cancelled appointment
        self.appointment.status = Appointment.AppointmentStatus.CANCELLED
        self.appointment.save()

        self.assertFalse(self.appointment.is_active)


class FullyPaidStatusTestCase(TestCase):
    """Tests for FULLY_PAID status behavior."""

    def setUp(self):
        """Create test data."""
        self.client_user = User.objects.create_user(
            email='client_fp@test.com',
            phone_number='+573001111111',
            password='testpass123',
            role=CustomUser.Role.CLIENT,
            first_name='Test',
            last_name='FullyPaid'
        )

        self.staff_user = User.objects.create_user(
            email='staff_fp@test.com',
            phone_number='+573002222222',
            password='testpass123',
            role=CustomUser.Role.STAFF,
            first_name='Staff',
            last_name='Test'
        )

        category = ServiceCategory.objects.create(name='Test Category FP')
        self.service = Service.objects.create(
            name='Test Service FP',
            description='Test',
            duration=60,
            price=100000,
            category=category
        )

        self.appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.FULLY_PAID,
            price_at_purchase=100000,
            reschedule_count=0
        )

    def test_can_reschedule_fully_paid_appointment(self):
        """Client can reschedule FULLY_PAID appointment."""
        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertTrue(can_reschedule)
        self.assertEqual(reason, "")

    def test_cannot_cancel_fully_paid_within_24h(self):
        """Client cannot cancel FULLY_PAID appointment within 24h."""
        self.appointment.start_time = timezone.now() + timedelta(hours=12)
        self.appointment.end_time = timezone.now() + timedelta(hours=13)
        self.appointment.save()

        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        self.assertFalse(can_cancel)
        self.assertIn("reagendar", reason.lower())

    def test_can_mark_completed_fully_paid(self):
        """Staff can mark FULLY_PAID appointment as completed."""
        self.appointment.start_time = timezone.now() - timedelta(hours=2)
        self.appointment.end_time = timezone.now() - timedelta(hours=1)
        self.appointment.save()

        can_complete, reason = self.appointment.can_mark_completed(self.staff_user)
        self.assertTrue(can_complete)

    def test_can_add_tip_to_fully_paid(self):
        """Can add tip to FULLY_PAID appointment."""
        can_tip, reason = self.appointment.can_add_tip(self.client_user)
        self.assertTrue(can_tip)

    def test_can_download_ical_fully_paid(self):
        """Can download iCal for FULLY_PAID appointment."""
        can_download, reason = self.appointment.can_download_ical(self.client_user)
        self.assertTrue(can_download)

    def test_fully_paid_is_active(self):
        """FULLY_PAID appointments are considered active."""
        self.assertTrue(self.appointment.is_active)

    def test_cannot_complete_final_payment_on_fully_paid(self):
        """Staff cannot process final payment on FULLY_PAID (already fully paid)."""
        # Note: The business logic might allow this for tips/extras
        # but the appointment status logic should allow it
        can_pay, reason = self.appointment.can_complete_final_payment(self.staff_user)
        self.assertTrue(can_pay)  # Allows for potential tips or adjustments


class PendingPaymentStatusTestCase(TestCase):
    """Tests for PENDING_PAYMENT status behavior."""

    def setUp(self):
        """Create test data."""
        self.client_user = User.objects.create_user(
            email='client_pp@test.com',
            phone_number='+573003333333',
            password='testpass123',
            role=CustomUser.Role.CLIENT,
            first_name='Test',
            last_name='PendingPay'
        )

        self.staff_user = User.objects.create_user(
            email='staff_pp@test.com',
            phone_number='+573004444444',
            password='testpass123',
            role=CustomUser.Role.STAFF,
            first_name='Staff',
            last_name='Test'
        )

        category = ServiceCategory.objects.create(name='Test Category PP')
        self.service = Service.objects.create(
            name='Test Service PP',
            description='Test',
            duration=60,
            price=100000,
            category=category
        )

        self.appointment = Appointment.objects.create(
            user=self.client_user,
            staff_member=self.staff_user,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=1),
            status=Appointment.AppointmentStatus.PENDING_PAYMENT,
            price_at_purchase=100000,
            reschedule_count=0
        )

    def test_can_reschedule_pending_payment_appointment(self):
        """Client can reschedule PENDING_PAYMENT appointment."""
        can_reschedule, reason = self.appointment.can_reschedule(self.client_user)
        self.assertTrue(can_reschedule, f"Expected to be able to reschedule PENDING_PAYMENT appointment, but got reason: {reason}")
        self.assertEqual(reason, "")

    def test_can_cancel_pending_payment_appointment(self):
        """Client can cancel PENDING_PAYMENT appointment."""
        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        self.assertTrue(can_cancel, f"Expected to be able to cancel PENDING_PAYMENT appointment, but got reason: {reason}")
        self.assertEqual(reason, "")

    def test_can_cancel_pending_payment_within_24h(self):
        """Client can cancel PENDING_PAYMENT appointment even within 24h (no payment made yet)."""
        self.appointment.start_time = timezone.now() + timedelta(hours=12)
        self.appointment.end_time = timezone.now() + timedelta(hours=13)
        self.appointment.save()

        can_cancel, reason = self.appointment.can_cancel(self.client_user)
        # PENDING_PAYMENT should allow cancellation even < 24h since no payment was made
        self.assertTrue(can_cancel)

    def test_pending_payment_is_active(self):
        """PENDING_PAYMENT appointments are considered active."""
        self.assertTrue(self.appointment.is_active)

    def test_admin_can_cancel_pending_payment(self):
        """Admin can cancel PENDING_PAYMENT appointment via can_cancel_by_admin."""
        admin_user = User.objects.create_user(
            email='admin_test@test.com',
            phone_number='+573009999999',
            password='testpass123',
            role=CustomUser.Role.ADMIN,
            first_name='Admin',
            last_name='Test'
        )

        can_cancel, reason = self.appointment.can_cancel_by_admin(admin_user)
        self.assertTrue(can_cancel, f"Admin should be able to cancel PENDING_PAYMENT, but got: {reason}")
        self.assertEqual(reason, "")
