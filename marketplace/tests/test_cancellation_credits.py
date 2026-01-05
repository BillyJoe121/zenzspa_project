from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from marketplace.models import Order, Product, ProductVariant, Cart, CartItem
from finances.models import ClientCredit, Payment
from marketplace.services import OrderService
from django.utils import timezone

User = get_user_model()

class OrderCancellationCreditsTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            phone_number='+573001234567',
            role='CLIENT',
            is_verified=True
        )
        self.client.force_authenticate(user=self.user)
        
        # Crear producto y variante
        self.product = Product.objects.create(
            name="Test Product",
            description="Desc",
            is_active=True
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal('10000.00'),
            stock=10,
            sku="TEST-SKU"
        )

    def test_cancellation_generates_credits_for_paid_order(self):
        # 1. Crear Orden PAID manualmente (simulando flujo completo)
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal('10000.00'),
            status=Order.OrderStatus.PENDING_PAYMENT
        )
        
        # Crear pago APROBADO asociado
        payment = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal('10000.00'),
            status=Payment.PaymentStatus.APPROVED,
            payment_type=Payment.PaymentType.ORDER,
            transaction_id="REF-123"
        )
        
        # Confirmar orden (esto valida que los pagos cubran el monto)
        OrderService.confirm_payment(order)
        self.assertEqual(order.status, Order.OrderStatus.PAID)
        
        # 2. Cancelar la orden vía API
        url = f'/api/v1/marketplace/orders/{order.id}/cancel/'
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        
        # 3. Verificar créditos generados
        credits = ClientCredit.objects.filter(user=self.user)
        self.assertEqual(credits.count(), 1)
        self.assertEqual(credits.first().initial_amount, Decimal('10000.00'))
        self.assertEqual(credits.first().originating_payment, payment)

    def test_cancellation_with_mixed_payment(self):
        # Caso de pago mixto: Crédito + Wompi
        order = Order.objects.create(
            user=self.user,
            total_amount=Decimal('20000.00'),
            status=Order.OrderStatus.PENDING_PAYMENT
        )
        
        # Pago 1: Crédito (5k)
        payment1 = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal('5000.00'),
            status=Payment.PaymentStatus.PAID_WITH_CREDIT, # Status correcto para pago con crédito
            payment_type=Payment.PaymentType.ORDER,
            transaction_id="CREDIT-REF-1"
        )
        
        # Pago 2: Wompi (15k)
        payment2 = Payment.objects.create(
            user=self.user,
            order=order,
            amount=Decimal('15000.00'),
            status=Payment.PaymentStatus.APPROVED,
            payment_type=Payment.PaymentType.ORDER,
            transaction_id="WOMPI-REF-2"
        )
        
        OrderService.confirm_payment(order)
        
        # Cancelar
        url = f'/api/v1/marketplace/orders/{order.id}/cancel/'
        self.client.post(url)
        
        # Verificar
        # Deberían generarse 2 créditos (uno por cada payment) o lógica consolidada?
        # La lógica actual es un crédito por cada pago.
        credits = ClientCredit.objects.filter(user=self.user).order_by('id')
        self.assertEqual(credits.count(), 2)
        
        amounts = sorted([c.initial_amount for c in credits])
        self.assertEqual(amounts, [Decimal('5000.00'), Decimal('15000.00')])

