from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from model_bakery import baker

from finances.views import PSEFinancialInstitutionsView


class PSEFinancialInstitutionsViewTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = baker.make("users.CustomUser")

    @mock.patch("finances.views.WompiPaymentClient.get_pse_financial_institutions")
    def test_returns_institutions_when_gateway_returns_list(self, mock_get):
        institutions = [
            {"financial_institution_code": "1", "financial_institution_name": "Banco Test 1"},
            {"financial_institution_code": "2", "financial_institution_name": "Banco Test 2"},
        ]
        mock_get.return_value = institutions

        request = self.factory.get("/api/finances/pse-banks/")
        force_authenticate(request, user=self.user)

        response = PSEFinancialInstitutionsView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, institutions)

    @mock.patch("finances.views.WompiPaymentClient.get_pse_financial_institutions")
    def test_propagates_status_code_when_gateway_returns_tuple(self, mock_get):
        mock_get.return_value = ({"error": "service_unavailable"}, 503)

        request = self.factory.get("/api/finances/pse-banks/")
        force_authenticate(request, user=self.user)

        response = PSEFinancialInstitutionsView.as_view()(request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"error": "No se pudieron obtener los bancos PSE"})
