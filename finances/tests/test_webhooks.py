import hashlib
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker

from finances.webhooks import WompiWebhookService
from finances.models import Payment


class WompiWebhookServiceTest(TestCase):
    def _build_signature(self, payload_data, timestamp, secret, properties):
        """Construye firma según el algoritmo oficial de Wompi con properties."""
        # Paso 1: Extraer valores según properties
        values = []
        for prop in properties:
            keys = prop.split(".")
            val = payload_data
            for key in keys:
                val = val.get(key) if isinstance(val, dict) else None
                if val is None:
                    break
            if val is not None:
                values.append(str(val))

        # Paso 2: Concatenar: valores + timestamp + secret
        concat = "".join(values) + str(timestamp) + secret

        # Paso 3: SHA256
        return hashlib.sha256(concat.encode("utf-8")).hexdigest()

    @override_settings(WOMPI_EVENT_SECRET="testsecret")
    def test_webhook_rejects_amount_mismatch(self):
        payment = baker.make(
            Payment,
            amount=100,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ADVANCE,
            transaction_id="REF-123",
        )

        transaction = {
            "id": "trans-123",
            "reference": "REF-123",
            "status": "APPROVED",
            "amount_in_cents": 10,  # incorrect
        }
        timestamp = int(timezone.now().timestamp())
        data = {"transaction": transaction}
        properties = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
        signature = self._build_signature(data, timestamp, "testsecret", properties)
        payload = {
            "data": data,
            "event": "transaction.updated",
            "signature": {
                "checksum": signature,
                "properties": properties
            },
            "timestamp": timestamp,
        }

        service = WompiWebhookService(payload, headers={})
        result = service.process_transaction_update()

        payment.refresh_from_db()
        self.assertEqual(result["status"], "amount_mismatch")
        self.assertEqual(payment.status, Payment.PaymentStatus.ERROR)

    @override_settings(WOMPI_EVENT_SECRET="testsecret")
    def test_webhook_rejects_stale_timestamp(self):
        payment = baker.make(
            Payment,
            amount=100,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.ADVANCE,
            transaction_id="REF-123",
        )
        transaction = {
            "id": "trans-123",
            "reference": "REF-123",
            "status": "APPROVED",
            "amount_in_cents": 10000,
        }
        old_timestamp = int(timezone.now().timestamp()) - 10000  # fuera de ventana
        data = {"transaction": transaction}
        properties = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
        signature = self._build_signature(data, old_timestamp, "testsecret", properties)
        payload = {
            "data": data,
            "event": "transaction.updated",
            "signature": {
                "checksum": signature,
                "properties": properties
            },
            "timestamp": old_timestamp,
        }
        service = WompiWebhookService(payload, headers={})
        with self.assertRaises(ValueError):
            service.process_transaction_update()
