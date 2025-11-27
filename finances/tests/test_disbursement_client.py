from decimal import Decimal
from unittest import mock
import requests

from django.test import TestCase, override_settings

from finances.services import WompiDisbursementClient, WompiPayoutError


class WompiDisbursementClientTests(TestCase):
    @override_settings(WOMPI_PAYOUT_PRIVATE_KEY="prv_x", WOMPI_PAYOUT_BASE_URL="https://api.example.com")
    @mock.patch("finances.services.requests.get")
    def test_get_available_balance_returns_decimal(self, mocked_get):
        mocked_get.return_value.status_code = 200
        mocked_get.return_value.json.return_value = {"data": [{"balanceInCents": 12345}]}
        client = WompiDisbursementClient()
        balance = client.get_available_balance()
        self.assertEqual(balance, Decimal("123.45"))

    @override_settings(WOMPI_PAYOUT_PRIVATE_KEY="prv_x", WOMPI_PAYOUT_BASE_URL="https://api.example.com")
    @mock.patch("finances.services.requests.get", side_effect=requests.Timeout)
    def test_get_available_balance_timeout_raises(self, mocked_get):
        client = WompiDisbursementClient()
        with self.assertRaises(WompiPayoutError):
            client.get_available_balance()
