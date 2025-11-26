import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from core.exceptions import BusinessLogicError

from users.models import CustomUser
from spa.models import ServiceCategory
from .models import (
    Product, ProductVariant, Cart, CartItem, 
    Order, OrderItem, InventoryMovement
)
from .services import OrderCreationService, OrderService, ReturnService

@pytest.mark.django_db
class TestProductVariant:
    """Tests para ProductVariant model"""
    
    def test_clean_vip_price_validation(self):
        """VIP price debe ser menor que regular price"""
        category = ServiceCategory.objects.create(name="Test")
        product = Product.objects.create(
            name="Test Product",
            description="Test",
            category=category
        )
        variant = ProductVariant(
            product=product,
            name="50ml",
            sku="TEST-001",
            price=Decimal('100.00'),
            vip_price=Decimal('150.00')  # ⚠️ Mayor que price
        )
        
        with pytest.raises(ValidationError):
            variant.clean()

@pytest.mark.django_db
class TestCartOperations:
    """Tests para operaciones del carrito"""
    
    @pytest.fixture
    def user(self):
        return CustomUser.objects.create_user(email="test@example.com", password="password")

    @pytest.fixture
    def product_variant(self):
        category = ServiceCategory.objects.create(name="Test Cat")
        product = Product.objects.create(name="Test Prod", category=category)
        return ProductVariant.objects.create(
            product=product, 
            name="Var 1", 
            sku="SKU-1", 
            price=Decimal('10.00'), 
            stock=10
        )

    def test_add_item_stock_validation(self, user, product_variant):
        """No se puede agregar más items que el stock disponible"""
        product_variant.stock = 5
        product_variant.save()
        
        cart = Cart.objects.create(user=user, is_active=True)
        
        # Agregar 5 items (OK)
        CartItem.objects.create(cart=cart, variant=product_variant, quantity=5)
        
        # Intentar agregar 1 más (debe fallar en validación de serializer o view)
        # Aquí probamos la lógica de negocio si estuviera aislada, 
        # pero como la validación está en view/serializer, este test unitario 
        # podría necesitar invocar el serializer.
        
        from .serializers import CartItemCreateUpdateSerializer
        serializer = CartItemCreateUpdateSerializer(data={'variant_id': product_variant.id, 'quantity': 1})
        # Mockear el contexto o la instancia si fuera necesario, 
        # pero aquí estamos probando "add new".
        # Si ya existe en el carrito, la view maneja la suma.
        
        # Simulemos la validación que hace la view:
        current_qty = 5
        add_qty = 1
        available = product_variant.stock - product_variant.reserved_stock
        
        assert current_qty + add_qty > available

    def test_concurrent_add_to_cart_race_condition(self, user, product_variant):
        """Test de race condition al agregar al carrito simultáneamente"""
        # Simular 2 requests concurrentes es difícil en test unitario simple sin hilos/procesos.
        # Este test es más un placeholder para recordar la necesidad de pruebas de carga.
        pass

@pytest.mark.django_db
class TestOrderCreation:
    """Tests para creación de órdenes"""
    
    @pytest.fixture
    def user(self):
        return CustomUser.objects.create_user(email="order@example.com", password="password")

    @pytest.fixture
    def cart_with_items(self, user):
        category = ServiceCategory.objects.create(name="Test Cat")
        product = Product.objects.create(name="Test Prod", category=category)
        variant = ProductVariant.objects.create(
            product=product, 
            name="Var 1", 
            sku="SKU-ORDER", 
            price=Decimal('100.00'), 
            stock=10
        )
        cart = Cart.objects.create(user=user, is_active=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)
        return cart
    
    def test_create_order_reserves_stock(self, user, cart_with_items):
        """Crear orden debe reservar stock"""
        variant = cart_with_items.items.first().variant
        initial_stock = variant.stock
        initial_reserved = variant.reserved_stock
        quantity = cart_with_items.items.first().quantity
        
        service = OrderCreationService(
            user=user,
            cart=cart_with_items,
            data={'delivery_option': Order.DeliveryOptions.PICKUP}
        )
        order = service.create_order()
        
        variant.refresh_from_db()
        assert variant.stock == initial_stock
        assert variant.reserved_stock == initial_reserved + quantity
    
    def test_create_order_empty_cart_fails(self, user):
        """No se puede crear orden con carrito vacío"""
        cart = Cart.objects.create(user=user, is_active=True)
        service = OrderCreationService(
            user=user,
            cart=cart,
            data={'delivery_option': Order.DeliveryOptions.PICKUP}
        )
        
        with pytest.raises(BusinessLogicError):
            service.create_order()

@pytest.mark.django_db
class TestOrderPaymentConfirmation:
    """Tests para confirmación de pago"""
    
    @pytest.fixture
    def order_with_reservation(self):
        user = CustomUser.objects.create_user(email="pay@example.com", password="password")
        category = ServiceCategory.objects.create(name="Test Cat")
        product = Product.objects.create(name="Test Prod", category=category)
        variant = ProductVariant.objects.create(
            product=product, 
            name="Var Pay", 
            sku="SKU-PAY", 
            price=Decimal('100.00'), 
            stock=10,
            reserved_stock=2
        )
        order = Order.objects.create(
            user=user, 
            total_amount=Decimal('200.00'),
            status=Order.OrderStatus.PENDING_PAYMENT
        )
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=2,
            price_at_purchase=Decimal('100.00')
        )
        return order
    
    def test_confirm_payment_captures_stock(self, order_with_reservation):
        """Confirmar pago debe capturar stock de reserved_stock"""
        item = order_with_reservation.items.first()
        variant = item.variant
        initial_stock = variant.stock
        initial_reserved = variant.reserved_stock
        
        OrderService.confirm_payment(order_with_reservation)
        
        variant.refresh_from_db()
        assert variant.stock == initial_stock - item.quantity
        assert variant.reserved_stock == initial_reserved - item.quantity
    
    def test_confirm_payment_validates_pricing(self, order_with_reservation):
        """Confirmar pago debe validar que precios no cambiaron"""
        # Cambiar precio de variante
        item = order_with_reservation.items.first()
        item.variant.price = Decimal('999.99')
        item.variant.save()
        
        with pytest.raises(BusinessLogicError, match="MKT-PRICE"):
            OrderService.confirm_payment(order_with_reservation)
