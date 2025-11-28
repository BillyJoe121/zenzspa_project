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

    @override_settings(
        WOMPI_PAYOUT_PRIVATE_KEY="prv_x",
        WOMPI_PAYOUT_BASE_URL="https://api.example.com",
        WOMPI_DEVELOPER_DESTINATION="dst_123",
    )
    @mock.patch("finances.services.requests.post")
    def test_create_payout_returns_transfer_id(self, mocked_post):
        mocked_post.return_value.status_code = 200
        mocked_post.return_value.json.return_value = {"data": {"id": "TRF_123"}}
        client = WompiDisbursementClient()
        transfer_id = client.create_payout(Decimal("100.00"))
        self.assertEqual(transfer_id, "TRF_123")

    @override_settings(
        WOMPI_PAYOUT_PRIVATE_KEY="prv_x",
        WOMPI_PAYOUT_BASE_URL="https://api.example.com",
        WOMPI_DEVELOPER_DESTINATION="dst_123",
    )
    @mock.patch("finances.services.requests.post")
    def test_create_payout_without_transfer_id_raises(self, mocked_post):
        mocked_post.return_value.status_code = 200
        mocked_post.return_value.json.return_value = {"data": {}}
        client = WompiDisbursementClient()
        with self.assertRaises(WompiPayoutError):
            client.create_payout(Decimal("100.00"))

    @override_settings(
        WOMPI_PAYOUT_PRIVATE_KEY="prv_x",
        WOMPI_PAYOUT_BASE_URL=None,
        WOMPI_DEVELOPER_DESTINATION="dst_123",
    )
    def test_create_payout_missing_base_url(self):
        client = WompiDisbursementClient()
        with self.assertRaises(WompiPayoutError):
            client.create_payout(Decimal("100.00"))
