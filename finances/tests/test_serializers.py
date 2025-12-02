from decimal import Decimal
from django.test import TestCase
from model_bakery import baker
from finances.serializers import (
    CommissionLedgerSerializer,
    PaymentSerializer,
    FinancialAdjustmentCreateSerializer,
    ClientCreditAdminSerializer,
)
from finances.models import CommissionLedger, Payment, ClientCredit, FinancialAdjustment
from users.models import CustomUser

class CommissionLedgerSerializerTest(TestCase):
    def test_get_pending_amount(self):
        ledger = baker.make(CommissionLedger, amount=Decimal("1000.00"), paid_amount=Decimal("200.00"))
        serializer = CommissionLedgerSerializer(ledger)
        self.assertEqual(serializer.data["pending_amount"], "800.00")
        self.assertEqual(serializer.data["amount"], "1000.00")

class PaymentSerializerTest(TestCase):
    def test_payment_serializer_fields(self):
        payment = baker.make(Payment)
        serializer = PaymentSerializer(payment)
        expected_fields = {
            "id", "user", "amount", "status", "payment_type", 
            "transaction_id", "raw_response", "created_at", "updated_at",
            "appointment", 
            "customer_legal_id", "customer_legal_id_type", "payment_method_type",
            "payment_method_data", "used_credit", "order",
            "tax_vat_in_cents", "tax_consumption_in_cents"
        }
        self.assertEqual(set(serializer.data.keys()), expected_fields)

class FinancialAdjustmentCreateSerializerTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser)
        self.payment = baker.make(Payment)

    def test_valid_data(self):
        data = {
            "user_id": self.user.id,
            "amount": "50.00",
            "adjustment_type": FinancialAdjustment.AdjustmentType.CREDIT,
            "reason": "Test adjustment",
            "related_payment_id": self.payment.id,
        }
        serializer = FinancialAdjustmentCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["user_id"], self.user)
        self.assertEqual(serializer.validated_data["related_payment_id"], self.payment)

    def test_invalid_user(self):
        data = {
            "user_id": "00000000-0000-0000-0000-000000000000",
            "amount": "50.00",
            "adjustment_type": FinancialAdjustment.AdjustmentType.CREDIT,
            "reason": "Test",
        }
        serializer = FinancialAdjustmentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_id", serializer.errors)

    def test_invalid_payment(self):
        data = {
            "user_id": self.user.id,
            "amount": "50.00",
            "adjustment_type": FinancialAdjustment.AdjustmentType.CREDIT,
            "reason": "Test",
            "related_payment_id": "00000000-0000-0000-0000-000000000000",
        }
        serializer = FinancialAdjustmentCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("related_payment_id", serializer.errors)

class ClientCreditAdminSerializerTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser)

    def test_validate_remaining_negative(self):
        data = {
            "user": self.user.id,
            "initial_amount": "100.00",
            "remaining_amount": "-10.00",
        }
        serializer = ClientCreditAdminSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("remaining_amount", serializer.errors)

    def test_validate_remaining_greater_than_initial(self):
        data = {
            "user": self.user.id,
            "initial_amount": "100.00",
            "remaining_amount": "150.00",
        }
        serializer = ClientCreditAdminSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("remaining_amount", serializer.errors)

    def test_create_sets_default_remaining(self):
        data = {
            "user": self.user.id,
            "initial_amount": "100.00",
        }
        serializer = ClientCreditAdminSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        credit = serializer.save()
        self.assertEqual(credit.remaining_amount, Decimal("100.00"))
