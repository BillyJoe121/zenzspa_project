from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from model_bakery import baker
from unittest import mock
from finances.tasks import (
    check_pending_payments,
    reconcile_recent_payments,
    process_recurring_subscriptions,
    downgrade_expired_vips,
    cleanup_old_webhook_events,
)
from finances.models import Payment, WebhookEvent
from users.models import CustomUser
from core.models import GlobalSettings

class FinancesTasksTest(TestCase):
    def setUp(self):
        self.user = baker.make(CustomUser, email="test@example.com")

    @mock.patch("finances.tasks.PaymentService.poll_pending_payment")
    def test_check_pending_payments(self, mock_poll):
        # Old pending payment
        old_payment = baker.make(
            Payment, 
            status=Payment.PaymentStatus.PENDING, 
            created_at=timezone.now() - timedelta(minutes=15)
        )
        # Recent pending payment (should be ignored)
        baker.make(
            Payment, 
            status=Payment.PaymentStatus.PENDING, 
            created_at=timezone.now() - timedelta(minutes=5)
        )
        
        mock_poll.return_value = True
        
        result = check_pending_payments()
        
        self.assertIn("Pagos pendientes revisados: 1", result)
        mock_poll.assert_called_once_with(old_payment)

    @mock.patch("finances.tasks.PaymentService.poll_pending_payment")
    def test_reconcile_recent_payments(self, mock_poll):
        payment = baker.make(
            Payment,
            status=Payment.PaymentStatus.PENDING,
            transaction_id="TRX123",
            created_at=timezone.now() - timedelta(hours=1)
        )
        mock_poll.return_value = True
        
        # Simulate status change side effect
        def side_effect(p):
            p.status = Payment.PaymentStatus.APPROVED
            p.save()
            return True
        mock_poll.side_effect = side_effect
        
        result = reconcile_recent_payments()
        
        self.assertIn("actualizados=1", result)

    @mock.patch("finances.tasks.PaymentService.charge_recurrence_token")
    @mock.patch("finances.tasks.PaymentService.apply_gateway_status")
    def test_process_recurring_subscriptions_success(self, mock_apply, mock_charge):
        settings = GlobalSettings.load()
        settings.vip_monthly_price = Decimal("100.00")
        settings.save()
        
        user = baker.make(
            CustomUser, 
            role=CustomUser.Role.VIP, 
            vip_auto_renew=True,
            vip_expires_at=timezone.now().date(),
            vip_payment_token="tok_123"
        )
        
        mock_charge.return_value = (Payment.PaymentStatus.APPROVED, {}, "REF123")
        mock_apply.return_value = Payment.PaymentStatus.APPROVED
        
        result = process_recurring_subscriptions()
        
        self.assertIn("Renovaciones intentadas: 1", result)
        user.refresh_from_db()
        self.assertEqual(user.vip_failed_payments, 0)

    @mock.patch("finances.tasks.PaymentService.charge_recurrence_token")
    @mock.patch("finances.tasks.PaymentService.apply_gateway_status")
    def test_process_recurring_subscriptions_failure(self, mock_apply, mock_charge):
        settings = GlobalSettings.load()
        settings.vip_monthly_price = Decimal("100.00")
        settings.save()
        
        user = baker.make(
            CustomUser, 
            role=CustomUser.Role.VIP, 
            vip_auto_renew=True,
            vip_expires_at=timezone.now().date(),
            vip_payment_token="tok_123",
            vip_failed_payments=2
        )
        
        mock_charge.return_value = (Payment.PaymentStatus.DECLINED, {}, "REF123")
        mock_apply.return_value = Payment.PaymentStatus.DECLINED
        
        process_recurring_subscriptions()
        
        user.refresh_from_db()
        self.assertEqual(user.vip_failed_payments, 3)
        self.assertFalse(user.vip_auto_renew)

    def test_downgrade_expired_vips(self):
        user = baker.make(
            CustomUser, 
            role=CustomUser.Role.VIP, 
            vip_expires_at=timezone.now().date() - timedelta(days=1)
        )
        
        result = downgrade_expired_vips()
        
        self.assertIn("Usuarios degradados: 1", result)
        user.refresh_from_db()
        self.assertEqual(user.role, CustomUser.Role.CLIENT)

    def test_cleanup_old_webhook_events(self):
        # Old processed event
        baker.make(
            WebhookEvent, 
            status=WebhookEvent.Status.PROCESSED, 
            created_at=timezone.now() - timedelta(days=100)
        )
        # Recent processed event
        baker.make(
            WebhookEvent, 
            status=WebhookEvent.Status.PROCESSED, 
            created_at=timezone.now() - timedelta(days=10)
        )
        
        result = cleanup_old_webhook_events()
        
        self.assertEqual(result["deleted_processed"], 1)
        self.assertEqual(WebhookEvent.objects.count(), 1)
