from unittest import mock

from django.test import TestCase, override_settings

from finances.gateway import WompiPaymentClient, build_integrity_signature


class WompiGatewayTests(TestCase):
    @override_settings(WOMPI_INTEGRITY_KEY="integrity123")
    def test_build_integrity_signature_uses_key(self):
        sig = build_integrity_signature("REF1", 1000, "COP")
        self.assertIsNotNone(sig)
        self.assertEqual(sig, build_integrity_signature("REF1", 1000, "COP"))

    @override_settings(WOMPI_BASE_URL="https://sandbox.wompi.co/v1", WOMPI_PUBLIC_KEY="pub_test_abc")
    @mock.patch("finances.gateway.requests.get")
    def test_resolve_acceptance_token_fetches_and_caches(self, mocked_get):
        mocked_get.return_value.status_code = 200
        mocked_get.return_value.json.return_value = {
            "data": {"presigned_acceptance": {"acceptance_token": "token123"}}
        }
        client = WompiPaymentClient()
        token = client.resolve_acceptance_token()
        self.assertEqual(token, "token123")
        # Segunda llamada debe usar cache y no reconsultar si ya se guardó
        token_again = client.resolve_acceptance_token()
        self.assertEqual(token_again, "token123")

    @override_settings(
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_PRIVATE_KEY="prv_test_123",
        WOMPI_CURRENCY="COP",
        WOMPI_INTEGRITY_KEY="test_integrity_123"
    )
    @mock.patch("finances.gateway.WompiPaymentClient.create_transaction")
    def test_create_pse_transaction(self, mock_create_transaction):
        """Test PSE transaction creation"""
        mock_create_transaction.return_value = (
            {"data": {"id": "1234-PSE", "status": "PENDING"}},
            201
        )

        client = WompiPaymentClient()
        response_data, status_code = client.create_pse_transaction(
            amount_in_cents=5000000,
            reference="PSE-TEST-001",
            customer_email="test@example.com",
            user_type=0,
            user_legal_id="1234567890",
            user_legal_id_type="CC",
            financial_institution_code="1",
            payment_description="Test PSE payment",
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(response_data["data"]["id"], "1234-PSE")
        mock_create_transaction.assert_called_once()

    @override_settings(
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_PRIVATE_KEY="prv_test_123",
        WOMPI_CURRENCY="COP",
        WOMPI_INTEGRITY_KEY="test_integrity_123"
    )
    @mock.patch("finances.gateway.WompiPaymentClient.create_transaction")
    def test_create_nequi_transaction(self, mock_create_transaction):
        """Test Nequi transaction creation"""
        mock_create_transaction.return_value = (
            {"data": {"id": "5678-NEQUI", "status": "PENDING"}},
            201
        )

        client = WompiPaymentClient()
        response_data, status_code = client.create_nequi_transaction(
            amount_in_cents=2500000,
            reference="NEQUI-TEST-001",
            customer_email="test@example.com",
            phone_number="3991111111",
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(response_data["data"]["id"], "5678-NEQUI")
        mock_create_transaction.assert_called_once()

    @override_settings(
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_PRIVATE_KEY="prv_test_123",
        WOMPI_CURRENCY="COP",
        WOMPI_INTEGRITY_KEY="test_integrity_123"
    )
    @mock.patch("finances.gateway.WompiPaymentClient.create_transaction")
    def test_create_daviplata_transaction(self, mock_create_transaction):
        """Test Daviplata transaction creation"""
        mock_create_transaction.return_value = (
            {"data": {"id": "9999-DAVI", "status": "PENDING"}},
            201
        )

        client = WompiPaymentClient()
        response_data, status_code = client.create_daviplata_transaction(
            amount_in_cents=1500000,
            reference="DAVI-TEST-001",
            customer_email="test@example.com",
            phone_number="3991111111",
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(response_data["data"]["id"], "9999-DAVI")
        mock_create_transaction.assert_called_once()

    @override_settings(
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_PUBLIC_KEY="pub_test_123"
    )
    @mock.patch("finances.gateway.requests.post")
    def test_tokenize_card(self, mock_post):
        """Test card tokenization"""
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {
            "status": "CREATED",
            "data": {
                "id": "tok_prod_123456_abcdef",
                "brand": "VISA",
                "last_four": "4242"
            }
        }

        client = WompiPaymentClient()
        result = client.tokenize_card(
            number="4242424242424242",
            cvc="123",
            exp_month="12",
            exp_year="25",
            card_holder="Juan Perez"
        )

        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["data"]["id"], "tok_prod_123456_abcdef")
        mock_post.assert_called_once()

    @override_settings(
        WOMPI_BASE_URL="https://sandbox.wompi.co/v1",
        WOMPI_PRIVATE_KEY="prv_test_123"
    )
    @mock.patch("finances.gateway.requests.post")
    def test_tokenize_nequi(self, mock_post):
        """Test Nequi tokenization"""
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {
            "status": "PENDING",
            "data": {
                "id": "tok_nequi_123456",
                "phone_number": "3991111111",
                "status": "PENDING"
            }
        }

        client = WompiPaymentClient()
        result = client.tokenize_nequi(phone_number="3991111111")

        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["data"]["id"], "tok_nequi_123456")
        mock_post.assert_called_once()

    @override_settings(WOMPI_BASE_URL="https://sandbox.wompi.co/v1")
    @mock.patch("finances.gateway.requests.get")
    def test_get_pse_financial_institutions(self, mock_get):
        """Test PSE banks list retrieval"""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": [
                {"financial_institution_code": "1", "financial_institution_name": "Banco Test 1"},
                {"financial_institution_code": "2", "financial_institution_name": "Banco Test 2"}
            ]
        }

        client = WompiPaymentClient()
        institutions = client.get_pse_financial_institutions()

        self.assertEqual(len(institutions), 2)
        self.assertEqual(institutions[0]["financial_institution_code"], "1")
        mock_get.assert_called_once()

    def test_build_integrity_signature_with_expiration_time(self):
        """Test integrity signature with expiration_time parameter"""
        with override_settings(WOMPI_INTEGRITY_KEY="test_integrity_123"):
            sig_without_expiration = build_integrity_signature("REF1", 1000, "COP")
            sig_with_expiration = build_integrity_signature(
                "REF1", 1000, "COP", expiration_time="2023-06-09T20:28:50.000Z"
            )

            self.assertIsNotNone(sig_without_expiration)
            self.assertIsNotNone(sig_with_expiration)
            self.assertNotEqual(sig_without_expiration, sig_with_expiration)
