
from unittest import mock
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from model_bakery import baker
from finances.models import Payment
from finances.views import PSEFinancialInstitutionsView

class PSEFinancialInstitutionsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", phone_number='+573001234567')
        self.client.force_authenticate(user=self.user)

    @mock.patch("finances.views.WompiPaymentClient.get_pse_financial_institutions")
    def test_returns_institutions_when_gateway_returns_list(self, mock_get):
        institutions = [
            {"financial_institution_code": "1", "financial_institution_name": "Banco Test 1"},
            {"financial_institution_code": "2", "financial_institution_name": "Banco Test 2"},
        ]
        mock_get.return_value = institutions

        url = reverse('pse-banks')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, institutions)

    @mock.patch("finances.views.WompiPaymentClient.get_pse_financial_institutions")
    def test_propagates_status_code_when_gateway_returns_tuple(self, mock_get):
        mock_get.return_value = ({"error": "service_unavailable"}, 503)

        url = reverse('pse-banks')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"error": "No se pudieron obtener los bancos PSE"})

class InitiateAppointmentPaymentViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", phone_number='+573001234567', is_verified=True)
        self.client.force_authenticate(user=self.user)
        self.appointment = baker.make("spa.Appointment", user=self.user, status="PENDING_PAYMENT")
        self.payment = baker.make("finances.Payment", appointment=self.appointment, status="PENDING", amount=10000)

    def test_initiate_payment_success(self):
        url = reverse('initiate-appointment-payment', args=[self.appointment.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("reference", response.data)
        self.assertIn("signature:integrity", response.data)

class InitiateVipSubscriptionViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", phone_number='+573001234567', is_verified=True)
        self.client.force_authenticate(user=self.user)
        # Ensure global settings has vip price
        from core.models import GlobalSettings
        settings = GlobalSettings.load()
        settings.vip_monthly_price = 50000
        settings.save()

    def test_initiate_vip_success(self):
        url = reverse('initiate-vip-subscription')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("reference", response.data)

class InitiatePackagePurchaseViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = baker.make("users.CustomUser", phone_number='+573001234567', is_verified=True)
        self.client.force_authenticate(user=self.user)
        self.package = baker.make("spa.Package")

    @mock.patch("finances.views.PaymentService.create_package_payment")
    def test_initiate_package_success(self, mock_create_payment):
        # Mock the payment creation to avoid database constraints if any
        mock_payment = baker.make("finances.Payment", amount=10000, transaction_id="REF123")
        mock_create_payment.return_value = mock_payment
        
        url = reverse('initiate-package-purchase')
        response = self.client.post(url, {"package_id": self.package.id})
        
        self.assertEqual(response.status_code, 200)

class WompiWebhookViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @mock.patch("finances.views.WompiWebhookService")
    def test_webhook_success(self, mock_service_cls):
        mock_service = mock_service_cls.return_value
        mock_service.event_type = "transaction.updated"
        mock_service.process_transaction_update.return_value = {"status": "ok"}
        
        url = reverse('wompi-webhook')
        response = self.client.post(url, {"event": "transaction.updated"}, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "webhook processed", "result": {"status": "ok"}})

    @mock.patch("finances.views.WompiWebhookService")
    def test_webhook_invalid_signature(self, mock_service_cls):
        mock_service_cls.side_effect = ValueError("Invalid signature")
        
        url = reverse('wompi-webhook')
        response = self.client.post(url, {"event": "test"}, format='json')
        
        self.assertEqual(response.status_code, 400)
