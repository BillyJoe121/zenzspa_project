from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from users.models import CustomUser
from marketplace.models import Product, ProductVariant

class CartPrivacyTest(APITestCase):
    def setUp(self):
        # Create users
        self.user_a = CustomUser.objects.create_user(
            phone_number='+573000000001',
            password='testpassword123',
            first_name='User A'
        )
        self.user_b = CustomUser.objects.create_user(
            phone_number='+573000000002',
            password='testpassword123',
            first_name='User B'
        )

        # Create products
        self.product = Product.objects.create(
            name="Test Product",
            description="Description",
            is_active=True,
            preparation_days=1
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product,
            name="Variant A",
            sku="SKU-A",
            price=10000,
            stock=100
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product,
            name="Variant B",
            sku="SKU-B",
            price=20000,
            stock=100
        )

        self.url = reverse('marketplace:cart-add-item')

    def test_idempotency_key_isolation(self):
        """
        Ensures that two different users using the SAME Idempotency-Key
        do NOT share the cached response.
        """
        shared_key = "universally-shared-key-123"

        # --- User A saves Variant A ---
        self.client.force_authenticate(user=self.user_a)
        data_a = {'variant_id': str(self.variant_a.id), 'quantity': 1}
        
        response_a = self.client.post(
            self.url, 
            data_a, 
            format='json', 
            headers={'Idempotency-Key': shared_key}
        )
        self.assertEqual(response_a.status_code, status.HTTP_201_CREATED)
        # Verify response contains Variant A
        self.assertEqual(len(response_a.data['items']), 1)
        self.assertEqual(response_a.data['items'][0]['variant']['id'], self.variant_a.id)

        # --- User B saves Variant B ---
        self.client.force_authenticate(user=self.user_b)
        data_b = {'variant_id': str(self.variant_b.id), 'quantity': 1}

        # IMPORTANT: Sending the SAME Idempotency-Key
        response_b = self.client.post(
            self.url, 
            data_b, 
            format='json', 
            headers={'Idempotency-Key': shared_key}
        )
        
        # If the bug exists, response_b would be the CACHED response_a (containing Variant A)
        # If fixed, it should be a NEW response (containing Variant B)
        self.assertEqual(response_b.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response_b.data['items']), 1)
        
        # Check that User B got Variant B, NOT Variant A
        variant_in_response = response_b.data['items'][0]['variant']['id']
        self.assertEqual(variant_in_response, self.variant_b.id, 
                         "User B received User A's cached cart response! Privacy leak detected.")
