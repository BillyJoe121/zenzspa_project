from django.test import TestCase
from django.core.cache import cache
from unittest import mock
import requests
from finances.gateway import WompiGateway, WompiPaymentClient

class WompiGatewayExtendedTest(TestCase):
    def setUp(self):
        self.gateway = WompiGateway(base_url="https://test.wompi.co")
        cache.clear()

    @mock.patch("requests.request")
    def test_request_with_retry_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = self.gateway._request_with_retry("GET", "https://test.wompi.co/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 1)

    @mock.patch("requests.request")
    def test_request_with_retry_timeout_then_success(self, mock_request):
        mock_request.side_effect = [requests.Timeout, mock.Mock(status_code=200)]
        response = self.gateway._request_with_retry("GET", "https://test.wompi.co/test", attempts=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

    @mock.patch("requests.request")
    def test_request_with_retry_max_retries(self, mock_request):
        mock_request.side_effect = requests.Timeout
        with self.assertRaises(requests.Timeout):
            self.gateway._request_with_retry("GET", "https://test.wompi.co/test", attempts=2)
        self.assertEqual(mock_request.call_count, 2)

    def test_circuit_breaker(self):
        # Simulate failures
        for _ in range(5):
            WompiGateway._record_failure(max_failures=5, cooldown_seconds=60)
        
        self.assertFalse(WompiGateway._circuit_allows())
        
        # Simulate cooldown passing (mocking time would be better but cache timeout works)
        # For this test we manually clear or wait, but since we can't wait, we check the state logic
        state = cache.get(WompiGateway._CIRCUIT_CACHE_KEY)
        self.assertIsNotNone(state["open_until"])

class WompiPaymentClientExtendedTest(TestCase):
    def setUp(self):
        self.client = WompiPaymentClient(base_url="https://test.wompi.co", private_key="prv_test")

    @mock.patch("requests.post")
    def test_tokenize_card_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"data": {"id": "tok_123"}}
        
        result = self.client.tokenize_card(
            number="4242424242424242",
            cvc="123",
            exp_month="12",
            exp_year="25",
            card_holder="John Doe"
        )
        self.assertEqual(result["data"]["id"], "tok_123")

    @mock.patch("requests.post")
    def test_tokenize_card_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Error")
        with self.assertRaises(requests.RequestException):
            self.client.tokenize_card(
                number="4242424242424242",
                cvc="123",
                exp_month="12",
                exp_year="25",
                card_holder="John Doe"
            )

    @mock.patch("requests.post")
    def test_create_payment_source_from_token(self, mock_post):
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"data": {"id": 123}}
        
        result = self.client.create_payment_source_from_token(
            token_id="tok_123",
            customer_email="test@example.com",
            acceptance_token="acc_123"
        )
        self.assertEqual(result["data"]["id"], 123)

    @mock.patch("requests.post")
    def test_create_payment_source_error(self, mock_post):
        mock_post.side_effect = requests.RequestException("Error")
        with self.assertRaises(requests.RequestException):
            self.client.create_payment_source_from_token(
                token_id="tok_123",
                customer_email="test@example.com",
                acceptance_token="acc_123"
            )
