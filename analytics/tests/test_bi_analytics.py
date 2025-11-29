from datetime import timedelta
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from users.models import CustomUser
from spa.models import Appointment, Service, ServiceCategory, WaitlistEntry
from marketplace.models import Product, ProductVariant, Order, OrderItem, InventoryMovement
from analytics.services import KpiService

class Analytics360Tests(APITestCase):
    def setUp(self):
        # Setup Admin User
        self.admin = CustomUser.objects.create_user(
            phone_number='+573001234567',
            email='admin@example.com',
            password='password123',
            role=CustomUser.Role.ADMIN,
            first_name='Admin',
            last_name='User'
        )
        self.client.force_authenticate(user=self.admin)
        
        # Dates
        self.today = timezone.localdate()
        self.start_date = self.today - timedelta(days=30)
        self.end_date = self.today

        # Setup Basic Data
        self.category = ServiceCategory.objects.create(name="Test Category")
        self.service = Service.objects.create(
            name="Test Service", 
            duration=60, 
            price=100.00, 
            category=self.category
        )
        
        # Create Appointments for Heatmap & Funnel
        # 1. Completed
        Appointment.objects.create(
            user=self.admin,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            status=Appointment.AppointmentStatus.COMPLETED,
            price_at_purchase=100.00
        )
        # 2. Confirmed
        Appointment.objects.create(
            user=self.admin,
            start_time=timezone.now() - timedelta(hours=2), # Within today
            end_time=timezone.now() - timedelta(hours=1),
            status=Appointment.AppointmentStatus.CONFIRMED,
            price_at_purchase=100.00
        )

    def test_heatmap_endpoint(self):
        url = reverse('analytics-ops-heatmap')
        response = self.client.get(url, {'start_date': self.start_date, 'end_date': self.end_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        # Should have data points
        self.assertTrue(len(response.data) > 0)
        first_point = response.data[0]
        self.assertIn('day', first_point)
        self.assertIn('hour', first_point)
        self.assertIn('value', first_point)

    def test_funnel_endpoint(self):
        url = reverse('analytics-ops-funnel')
        response = self.client.get(url, {'start_date': self.start_date, 'end_date': self.end_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('steps', response.data)
        self.assertIn('conversion_rate', response.data)
        
        steps = response.data['steps']
        self.assertEqual(len(steps), 3) # Solicitadas, Confirmadas, Completadas
        self.assertEqual(steps[0]['name'], 'Solicitadas')
        self.assertTrue(steps[0]['value'] >= 2) # At least the 2 we created

    def test_waitlist_endpoint(self):
        # Create Waitlist Entry
        WaitlistEntry.objects.create(
            user=self.admin,
            desired_date=self.today,
            status=WaitlistEntry.Status.WAITING
        ).services.add(self.service)

        url = reverse('analytics-bi-waitlist')
        response = self.client.get(url, {'start_date': self.start_date, 'end_date': self.end_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_entries', response.data)
        self.assertIn('estimated_lost_revenue', response.data)
        self.assertEqual(response.data['total_entries'], 1)
        self.assertEqual(float(response.data['estimated_lost_revenue']), 100.0)

    def test_inventory_endpoint(self):
        # Setup Product
        product = Product.objects.create(name="Test Product")
        variant = ProductVariant.objects.create(product=product, name="Var 1", sku="SKU1", price=50, stock=10)
        
        # Create Order Item (Sale)
        order = Order.objects.create(user=self.admin, total_amount=50)
        OrderItem.objects.create(order=order, variant=variant, quantity=2, price_at_purchase=50)
        
        # Create Shrinkage (Adjustment)
        InventoryMovement.objects.create(
            variant=variant,
            quantity=-1,
            movement_type=InventoryMovement.MovementType.ADJUSTMENT
        )

        url = reverse('analytics-bi-inventory')
        response = self.client.get(url, {'start_date': self.start_date, 'end_date': self.end_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('top_products', response.data)
        self.assertIn('shrinkage_items', response.data)
        
        self.assertEqual(len(response.data['top_products']), 1)
        self.assertEqual(response.data['shrinkage_items'], 1)

    def test_growth_endpoint(self):
        url = reverse('analytics-bi-growth')
        response = self.client.get(url, {'start_date': self.start_date, 'end_date': self.end_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('revenue', response.data)
        self.assertIn('appointments', response.data)
        self.assertIn('growth_rate', response.data['revenue'])
