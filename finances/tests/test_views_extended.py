from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from model_bakery import baker
from unittest import mock
from finances.models import CommissionLedger, Payment, ClientCredit
from core.models import GlobalSettings

class CommissionLedgerListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", role="ADMIN")
        self.client.force_authenticate(user=self.user)
        self.ledger1 = baker.make(CommissionLedger, status="PENDING", created_at="2023-01-01")
        self.ledger2 = baker.make(CommissionLedger, status="PAID", created_at="2023-02-01")

    def test_filter_by_status(self):
        url = reverse("commission-ledger-list") + "?status=PENDING"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(str(response.data["results"][0]["id"]), str(self.ledger1.id))

    def test_filter_by_date_range(self):
        url = reverse("commission-ledger-list") + "?start_date=2023-01-01&end_date=2023-01-31"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(str(response.data["results"][0]["id"]), str(self.ledger1.id))

class DeveloperCommissionStatusViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", role="ADMIN")
        self.client.force_authenticate(user=self.user)
        GlobalSettings.load()

    @mock.patch("finances.views.WompiDisbursementClient")
    def test_get_status_success(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get_available_balance.return_value = Decimal("1000.00")
        
        url = reverse("commission-ledger-status")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["wompi_available_balance"], "1000.00")

    @mock.patch("finances.views.WompiDisbursementClient")
    def test_get_status_exception_handling(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get_available_balance.side_effect = Exception("API Error")
        
        url = reverse("commission-ledger-status")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["wompi_available_balance"], "0.00")

# ... (CreatePaymentViewsTest unchanged) ...

class ClientCreditAdminViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = baker.make("users.CustomUser", role="ADMIN")
        self.client.force_authenticate(user=self.admin)
        self.user = baker.make("users.CustomUser")

    def test_create_credit_computes_status(self):
        url = reverse("admin-client-credit-list")
        data = {
            "user": self.user.id,
            "initial_amount": "100.00"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], ClientCredit.CreditStatus.AVAILABLE)

    def test_update_credit_recomputes_status(self):
        credit = baker.make(ClientCredit, user=self.user, initial_amount=100, remaining_amount=100, status="AVAILABLE")
        url = reverse("admin-client-credit-detail", args=[credit.id])
        data = {
            "user": self.user.id,
            "initial_amount": "100.00",
            "remaining_amount": "0.00"
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], ClientCredit.CreditStatus.USED)
