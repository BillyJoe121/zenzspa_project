from decimal import Decimal
from django.test import TestCase
from django.core.cache import cache
from django.utils import timezone
from model_bakery import baker
from unittest import mock
import requests
from finances.services import (
    WompiDisbursementClient,
    WompiPayoutError,
    DeveloperCommissionService,
    FinancialAdjustmentService,
    CreditManagementService,
)
from finances.models import CommissionLedger, FinancialAdjustment, ClientCredit, Payment
from core.models import GlobalSettings, AuditLog
from users.models import CustomUser

class WompiDisbursementClientTest(TestCase):
    def setUp(self):
        self.client = WompiDisbursementClient()
        self.client.base_url = "https://test.wompi.co"
        self.client.private_key = "prv_test"
        self.client.destination = "dest_123"
        self.client.balance_endpoint = "https://test.wompi.co/accounts"
        self.client.payout_endpoint = "https://test.wompi.co/transfers"
        cache.clear()

    @mock.patch("requests.request")
    def test_get_available_balance_success(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "data": {"accounts": [{"balanceInCents": 100000}]}
        }
        balance = self.client.get_available_balance()
        self.assertEqual(balance, Decimal("1000.00"))

    @mock.patch("requests.request")
    def test_get_available_balance_error(self, mock_request):
        mock_request.side_effect = requests.RequestException("Error")
        with self.assertRaises(WompiPayoutError):
            self.client.get_available_balance()

    @mock.patch("requests.request")
    def test_create_payout_success(self, mock_request):
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {
            "data": {"id": "trf_123"}
        }
        transfer_id = self.client.create_payout(Decimal("100.00"))
        self.assertEqual(transfer_id, "trf_123")

    @mock.patch("requests.request")
    def test_create_payout_error(self, mock_request):
        mock_request.side_effect = requests.RequestException("Error")
        with self.assertRaises(WompiPayoutError):
            self.client.create_payout(Decimal("100.00"))

class DeveloperCommissionServiceTest(TestCase):
    def setUp(self):
        self.settings = GlobalSettings.load()
        self.settings.developer_commission_percentage = 10
        self.settings.developer_payout_threshold = 500
        self.settings.save()
        self.payment = baker.make(Payment, amount=1000)

    def test_register_commission(self):
        ledger = DeveloperCommissionService.register_commission(self.payment)
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.amount, Decimal("100.00"))
        self.assertEqual(ledger.status, CommissionLedger.Status.PENDING)

    def test_get_developer_debt(self):
        baker.make(CommissionLedger, amount=Decimal("100.00"), paid_amount=Decimal("0.00"), status=CommissionLedger.Status.PENDING)
        baker.make(CommissionLedger, amount=Decimal("200.00"), paid_amount=Decimal("50.00"), status=CommissionLedger.Status.PENDING)
        debt = DeveloperCommissionService.get_developer_debt()
        self.assertEqual(debt, Decimal("250.00"))

    @mock.patch("finances.services.WompiDisbursementClient")
    def test_evaluate_payout_below_threshold(self, mock_client_cls):
        baker.make(CommissionLedger, amount=Decimal("100.00"), paid_amount=Decimal("0.00"), status=CommissionLedger.Status.PENDING)
        result = DeveloperCommissionService.evaluate_payout()
        self.assertEqual(result["status"], "below_threshold")

    @mock.patch("finances.services.WompiDisbursementClient")
    def test_evaluate_payout_success(self, mock_client_cls):
        baker.make(CommissionLedger, amount=Decimal("1000.00"), paid_amount=Decimal("0.00"), status=CommissionLedger.Status.PENDING)
        mock_client = mock_client_cls.return_value
        mock_client.get_available_balance.return_value = Decimal("2000.00")
        mock_client.create_payout.return_value = "trf_123"
        
        result = DeveloperCommissionService.evaluate_payout()
        self.assertEqual(result["status"], "paid")
        self.assertEqual(result["amount"], "1000.00")

class FinancialAdjustmentServiceTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser)
        self.admin = baker.make(CustomUser, is_staff=True)

    def test_create_adjustment_credit(self):
        adj = FinancialAdjustmentService.create_adjustment(
            user=self.user,
            amount=Decimal("100.00"),
            adjustment_type=FinancialAdjustment.AdjustmentType.CREDIT,
            reason="Refund",
            created_by=self.admin
        )
        self.assertEqual(adj.amount, Decimal("100.00"))
        self.assertTrue(ClientCredit.objects.filter(user=self.user, initial_amount=100).exists())

    def test_create_adjustment_limit_exceeded(self):
        from core.utils.exceptions import BusinessLogicError
        with self.assertRaises(BusinessLogicError):
            FinancialAdjustmentService.create_adjustment(
                user=self.user,
                amount=Decimal("6000000.00"),
                adjustment_type=FinancialAdjustment.AdjustmentType.CREDIT,
                reason="Big Refund",
                created_by=self.admin
            )

class CreditManagementServiceTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser)
        self.admin = baker.make(CustomUser, is_staff=True)
        self.appointment = baker.make("spa.Appointment", user=self.user)

    def test_issue_credit_from_appointment(self):
        payment = baker.make(
            Payment, 
            user=self.user, 
            appointment=self.appointment, 
            amount=100, 
            payment_type=Payment.PaymentType.ADVANCE,
            status=Payment.PaymentStatus.APPROVED
        )
        total, credits = CreditManagementService.issue_credit_from_appointment(
            appointment=self.appointment,
            percentage=0.5,
            created_by=self.admin,
            reason="Partial refund"
        )
        self.assertEqual(total, Decimal("50.00"))
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0].initial_amount, Decimal("50.00"))

    def test_apply_cancellation_penalty(self):
        credit = baker.make(ClientCredit, user=self.user, status=ClientCredit.CreditStatus.AVAILABLE, remaining_amount=100)
        history = [{"credit_id": credit.id}, {"credit_id": None}, {"credit_id": None}]
        
        CreditManagementService.apply_cancellation_penalty(self.user, self.appointment, history)
        
        credit.refresh_from_db()
        self.assertEqual(credit.status, ClientCredit.CreditStatus.EXPIRED)
        self.assertEqual(credit.remaining_amount, Decimal("0.00"))
