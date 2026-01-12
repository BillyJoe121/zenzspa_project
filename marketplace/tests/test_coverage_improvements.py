import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from marketplace.models import (
    Product, ProductVariant, ProductImage, Order, OrderItem, 
    ProductReview, Cart, CartItem, InventoryMovement
)
from users.models import CustomUser
from spa.models import Appointment, ServiceCategory

@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        phone_number="+573001112233",
        email="user@example.com",
        password="password",
        first_name="User"
    )

@pytest.fixture
def admin_user(db):
    return CustomUser.objects.create_superuser(
        phone_number="+573009998877",
        email="admin@example.com",
        password="password",
        first_name="Admin"
    )

@pytest.fixture
def product(db):
    return Product.objects.create(name="Test Product", description="Desc", preparation_days=1)

@pytest.fixture
def variant(db, product):
    return ProductVariant.objects.create(
        product=product, name="Var 1", sku="SKU1", price=Decimal("100.00"), stock=10
    )

from rest_framework.test import APIClient

@pytest.fixture
def api_client():
    return APIClient()

@pytest.mark.django_db
class TestModelCoverage:
    def test_product_image_str_and_clean(self, product):
        # Valid image (50x50 pixel PNG)
        from PIL import Image
        import io
        
        img_io = io.BytesIO()
        image = Image.new('RGB', (50, 50), color='red')
        image.save(img_io, format='PNG')
        image_content = img_io.getvalue()
        
        file = SimpleUploadedFile("test.png", image_content, content_type="image/png")
        img = ProductImage(product=product, image=file)
        img.clean() # Should pass
        img.save()
        assert str(img) == f"Imagen para {product.name}"

        # Invalid extension
        file_bad_ext = SimpleUploadedFile("test.txt", b"content", content_type="image/png")
        img_bad = ProductImage(product=product, image=file_bad_ext)
        with pytest.raises(ValidationError, match="Extensión de archivo no permitida"):
            img_bad.clean()

        # Invalid content type
        file_bad_type = SimpleUploadedFile("test.png", b"content", content_type="text/plain")
        img_bad_type = ProductImage(product=product, image=file_bad_type)
        with pytest.raises(ValidationError, match="No se pudo validar la imagen|Formato de imagen no permitido"):
            img_bad_type.clean()

    def test_order_clean_address(self, user):
        order = Order(
            user=user, 
            total_amount=Decimal("100"), 
            delivery_option=Order.DeliveryOptions.DELIVERY,
            delivery_address="Short"
        )
        with pytest.raises(ValidationError, match="al menos 15 caracteres"):
            order.clean()

        order.delivery_address = "Calle 123 sin numero"
        with pytest.raises(ValidationError, match="formato de nomenclatura"):
            order.clean()

        order.delivery_address = "Calle 123 # 45-67"
        order.clean() # Should pass

    def test_order_item_str(self, user, variant):
        order = Order.objects.create(user=user, total_amount=Decimal("100"))
        item = OrderItem.objects.create(order=order, variant=variant, quantity=2, price_at_purchase=Decimal("100"))
        assert str(item) == f"2 x {variant}"

    def test_product_review_str_clean_save(self, user, product, variant):
        # Create order for verified purchase
        order = Order.objects.create(
            user=user, 
            total_amount=Decimal("100"), 
            status=Order.OrderStatus.DELIVERED
        )
        OrderItem.objects.create(order=order, variant=variant, quantity=1, price_at_purchase=Decimal("100"))

        review = ProductReview(
            user=user, 
            product=product, 
            order=order,
            rating=5, 
            comment="Great!"
        )
        review.save()
        assert review.is_verified_purchase
        assert str(review) == f"Reseña de {user.email} para {product.name} - 5⭐"

        # Invalid rating
        review.rating = 6
        with pytest.raises(ValidationError, match="entre 1 y 5"):
            review.clean()

        # Missing content
        review.rating = 5
        review.title = ""
        review.comment = ""
        with pytest.raises(ValidationError, match="título o un comentario"):
            review.clean()

@pytest.mark.django_db
class TestViewCoverage:
    def test_product_viewset_filters(self, api_client, product, variant):
        # Setup data
        cat = ServiceCategory.objects.create(name="Cat 1")
        product.category = cat
        product.save()
        
        url = '/api/v1/marketplace/products/'
        
        # Search
        response = api_client.get(url, {'search': 'Test'})
        assert len(response.data['results']) == 1
        
        # Category
        response = api_client.get(url, {'category': str(cat.id)})
        assert len(response.data['results']) == 1
        
        # Price range
        response = api_client.get(url, {'min_price': '50', 'max_price': '150'})
        assert len(response.data['results']) == 1
        
        # Stock
        response = api_client.get(url, {'in_stock': 'true'})
        assert len(response.data['results']) == 1

    def test_product_reviews_action(self, api_client, product, user):
        ProductReview.objects.create(user=user, product=product, rating=5, comment="Good", is_approved=True)
        url = f'/api/v1/marketplace/products/{product.id}/reviews/'
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_cart_add_item_limits(self, api_client, user, variant):
        api_client.force_authenticate(user=user)
        url = '/api/v1/marketplace/cart/add-item/'
        
        # Max quantity per item
        response = api_client.post(url, {'variant_id': str(variant.id), 'quantity': 101})
        assert response.status_code == 400
        # Check for error in response data (could be dict with 'error' or list of errors)
        if 'error' in response.data:
            assert "cantidad máxima" in response.data['error']
        else:
            # Serializer error
            assert 'quantity' in response.data or 'non_field_errors' in response.data

        # Stock limit
        variant.stock = 5
        variant.save()
        response = api_client.post(url, {'variant_id': str(variant.id), 'quantity': 6})
        assert response.status_code == 400
        if 'error' in response.data:
            assert "Stock insuficiente" in response.data['error']

    def test_cart_checkout_errors(self, api_client, user, variant):
        api_client.force_authenticate(user=user)
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)
        
        url = '/api/v1/marketplace/cart/checkout/'
        
        # Invalid appointment
        data = {
            'delivery_option': Order.DeliveryOptions.ASSOCIATE_TO_APPOINTMENT,
            'associated_appointment_id': '00000000-0000-0000-0000-000000000000' # Non-existent
        }
        response = api_client.post(url, data)
        assert response.status_code == 400
        assert "cita asociada no es válida" in response.data['error']

    def test_product_review_viewset_crud(self, api_client, user, product):
        api_client.force_authenticate(user=user)
        
        # Create
        url = '/api/v1/marketplace/reviews/'
        data = {'product': str(product.id), 'rating': 5, 'comment': 'Nice'}
        response = api_client.post(url, data)
        assert response.status_code == 201
        
        # Fetch created review
        review = ProductReview.objects.get(user=user, product=product)
        review_id = review.id
        
        # Update own
        url_detail = f'/api/v1/marketplace/reviews/{review_id}/'
        response = api_client.patch(url_detail, {'comment': 'Updated'})
        assert response.status_code == 200
        
        # List my reviews
        response = api_client.get('/api/v1/marketplace/reviews/my_reviews/')
        assert response.status_code == 200
        assert len(response.data) == 1

        # Delete own
        response = api_client.delete(url_detail)
        assert response.status_code == 204

    def test_product_review_admin_actions(self, api_client, admin_user, user, product):
        review = ProductReview.objects.create(user=user, product=product, rating=4, comment="Ok", is_approved=False)
        
        api_client.force_authenticate(user=admin_user)
        
        # Respond
        url = f'/api/v1/marketplace/reviews/{review.id}/respond/'
        data = {'admin_response': 'Thanks', 'is_approved': True}
        response = api_client.post(url, data)
        assert response.status_code == 200
        review.refresh_from_db()
        assert review.is_approved
        assert review.admin_response == 'Thanks'

    def test_admin_inventory_movement_reserved(self, api_client, admin_user, variant):
        api_client.force_authenticate(user=admin_user)
        url = '/api/v1/marketplace/admin/inventory-movements/'
        
        # Test reservation movement (should affect reserved_stock)
        data = {
            'variant': str(variant.id),
            'quantity': 2,
            'movement_type': InventoryMovement.MovementType.RESERVATION
        }
        response = api_client.post(url, data)
        assert response.status_code == 201
        
        variant.refresh_from_db()
        assert variant.reserved_stock == 2

    def test_order_viewset_process_return(self, api_client, admin_user, user, variant):
        order = Order.objects.create(user=user, total_amount=Decimal("100"), status=Order.OrderStatus.RETURN_REQUESTED)
        item = OrderItem.objects.create(order=order, variant=variant, quantity=1, price_at_purchase=Decimal("100"))
        order.return_request_data = [{'order_item_id': str(item.id), 'quantity': 1}]
        order.save()

        api_client.force_authenticate(user=admin_user)
        url = f'/api/v1/marketplace/orders/{order.id}/process-return/'
        
        response = api_client.post(url, {'approved': True})
        assert response.status_code == 200
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.REFUNDED
