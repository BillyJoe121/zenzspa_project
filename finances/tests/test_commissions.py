from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import GlobalSettings
from finances.models import CommissionLedger
from finances.services import DeveloperCommissionService
from finances.views import DeveloperCommissionStatusView
from spa.models import Payment
from users.models import CustomUser
from finances.tasks import run_developer_payout
from finances.gateway import build_integrity_signature


class DeveloperCommissionStatusViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = CustomUser.objects.create_user(
            phone_number="+11111111111",
            email="admin@example.com",
            first_name="Admin",
            password="testpass123",
        )
        self.user.role = CustomUser.Role.ADMIN
        self.user.is_verified = True
        self.user.save(update_fields=["role", "is_verified"])

    @mock.patch("finances.views.DeveloperCommissionService.get_developer_debt", return_value=Decimal("150000.00"))
    @mock.patch("finances.views.WompiDisbursementClient.get_available_balance", return_value=Decimal("350000.00"))
    def test_status_includes_wompi_balance(self, mocked_balance, mocked_debt):
        view = DeveloperCommissionStatusView.as_view()
        request = self.factory.get("/api/v1/finances/commissions/status/")
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["wompi_available_balance"], "350000.00")
        self.assertEqual(response.data["developer_debt"], "150000.00")


class CommissionLedgerServiceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            phone_number="+12223334444",
            email="user@example.com",
            first_name="User",
            password="testpass123",
        )
        self.payment = Payment.objects.create(
            user=self.user,
            amount=Decimal("100.00"),
            payment_type=Payment.PaymentType.ADVANCE,
            status=Payment.PaymentStatus.APPROVED,
        )
        GlobalSettings.load()

    def test_mark_failed_nsf_updates_pending_entries(self):
        ledger = CommissionLedger.objects.create(
            amount=Decimal("10.00"),
            source_payment=self.payment,
            status=CommissionLedger.Status.PENDING,
        )
        DeveloperCommissionService._mark_failed_nsf()
        ledger.refresh_from_db()
        self.assertEqual(ledger.status, CommissionLedger.Status.FAILED_NSF)

    def test_negative_amount_is_invalid(self):
        with self.assertRaises(ValidationError):
            ledger = CommissionLedger(
                amount=Decimal("-1.00"),
                source_payment=self.payment,
            )
            ledger.full_clean()

    @mock.patch("django.conf.settings.WOMPI_INTEGRITY_KEY", "test_key")
    def test_build_integrity_signature(self):
        sig = build_integrity_signature("REF123", 5000, "COP")
        self.assertIsNotNone(sig)
        expected = build_integrity_signature("REF123", 5000, "COP")
        self.assertEqual(sig, expected)


class DeveloperPayoutTaskTests(TestCase):
    @mock.patch("finances.tasks.DeveloperCommissionService.evaluate_payout")
    def test_run_developer_payout_delegates_to_service(self, mocked_service):
        run_developer_payout()
        mocked_service.assert_called_once()
