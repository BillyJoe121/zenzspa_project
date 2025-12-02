from django.test import TestCase
from model_bakery import baker
from unittest import mock
from finances.webhooks import WompiWebhookService
from finances.models import PaymentToken, CommissionLedger, WebhookEvent
from users.models import CustomUser

class WompiWebhookServiceExtendedTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser, email="test@example.com", phone_number="3001234567")

    @mock.patch("finances.webhooks.WompiWebhookService._validate_signature")
    def test_process_token_update_success(self, mock_validate):
        data = {
            "event": "nequi_token.updated",
            "timestamp": 1234567890,
            "signature": {"checksum": "fake"},
            "data": {
                "token": {
                    "id": "tok_123",
                    "status": "APPROVED",
                    "type": "NEQUI",
                    "phone_number": "3001234567",
                    "customer_email": "test@example.com"
                }
            }
        }
        service = WompiWebhookService(data)
        result = service.process_token_update()
        
        self.assertEqual(result["status"], "token_event_processed")
        fingerprint = PaymentToken.fingerprint("tok_123")
        self.assertTrue(PaymentToken.objects.filter(token_fingerprint=fingerprint).exists())
        token = PaymentToken.objects.get(token_fingerprint=fingerprint)
        self.assertEqual(token.user, self.user)
        self.assertEqual(token.status, "APPROVED")

    @mock.patch("finances.webhooks.WompiWebhookService._validate_signature")
    def test_process_token_update_missing_id(self, mock_validate):
        data = {
            "event": "nequi_token.updated",
            "timestamp": 1234567890,
            "signature": {"checksum": "fake"},
            "data": {"token": {}}
        }
        service = WompiWebhookService(data)
        with self.assertRaisesRegex(ValueError, "No se encontró token_id"):
            service.process_token_update()
        
        self.assertEqual(service.event_record.status, WebhookEvent.Status.FAILED)

    @mock.patch("finances.webhooks.WompiWebhookService._validate_signature")
    def test_process_payout_update_approved(self, mock_validate):
        ledger = baker.make(CommissionLedger, wompi_transfer_id="TRF123", status="PENDING")
        data = {
            "event": "transfer.updated",
            "timestamp": 1234567890,
            "signature": {"checksum": "fake"},
            "data": {
                "transfer": {
                    "id": "TRF123",
                    "status": "APPROVED"
                }
            }
        }
        service = WompiWebhookService(data)
        result = service.process_payout_update()
        
        self.assertEqual(result["status"], "payout_event_processed")
        ledger.refresh_from_db()
        self.assertEqual(ledger.status, CommissionLedger.Status.PAID)

    @mock.patch("finances.webhooks.WompiWebhookService._validate_signature")
    def test_process_payout_update_declined(self, mock_validate):
        ledger = baker.make(CommissionLedger, wompi_transfer_id="TRF123", status="PENDING")
        data = {
            "event": "transfer.updated",
            "timestamp": 1234567890,
            "signature": {"checksum": "fake"},
            "data": {
                "transfer": {
                    "id": "TRF123",
                    "status": "DECLINED"
                }
            }
        }
        service = WompiWebhookService(data)
        result = service.process_payout_update()
        
        self.assertEqual(result["status"], "payout_event_processed")
        ledger.refresh_from_db()
        self.assertEqual(ledger.status, CommissionLedger.Status.FAILED_NSF)

    @mock.patch("finances.webhooks.WompiWebhookService._validate_signature")
    def test_process_payout_update_missing_id(self, mock_validate):
        data = {
            "event": "transfer.updated",
            "timestamp": 1234567890,
            "signature": {"checksum": "fake"},
            "data": {"transfer": {}}
        }
        service = WompiWebhookService(data)
        with self.assertRaisesRegex(ValueError, "transfer_id o status no presentes"):
            service.process_payout_update()
        
        self.assertEqual(service.event_record.status, WebhookEvent.Status.FAILED)
