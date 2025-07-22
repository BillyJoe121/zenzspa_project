from rest_framework import serializers
from .models import Product, ProductImage, Cart, CartItem, Order, OrderItem
from users.models import CustomUser

# --- Serializadores de Lectura (Para mostrar datos) ---

class ProductImageSerializer(serializers.ModelSerializer):
    """Serializador para las imágenes de un producto."""
    class Meta:
        model = ProductImage
        fields = ['image', 'is_primary', 'alt_text']

class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializador para listar productos en el catálogo.
    Muestra solo la imagen principal para mantener la respuesta ligera.
    """
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'vip_price', 'stock', 'main_image']

    def get_main_image(self, obj):
        # Busca la imagen marcada como principal o la primera que encuentre
        primary_image = obj.images.filter(is_primary=True).first()
        if not primary_image:
            primary_image = obj.images.first()
        if primary_image:
            return ProductImageSerializer(primary_image).data
        return None

class ProductDetailSerializer(ProductListSerializer):
    """
    Serializador para ver el detalle de un solo producto.
    Muestra todas las imágenes y la descripción completa.
    """
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'vip_price', 'stock',
            'category', 'preparation_days', 'images'
        ]

class CartItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de un carrito."""
    product = ProductListSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'subtotal']

    def get_subtotal(self, obj):
        # Calcula el subtotal basado en el rol del usuario que ve el carrito
        user = self.context['request'].user
        price = obj.product.price
        if user.is_vip and obj.product.vip_price:
            price = obj.product.vip_price
        return obj.quantity * price

class CartSerializer(serializers.ModelSerializer):
    """Serializador para mostrar el contenido completo del carrito de un usuario."""
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'is_active', 'items', 'total']
    
    def get_total(self, obj):
        # Suma los subtotales de todos los ítems para obtener el total del carrito
        return sum(self.context['view'].get_serializer(item).data['subtotal'] for item in obj.items.all())

# --- Serializadores de Escritura (Para crear/actualizar datos) ---

class CartItemCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para añadir o actualizar un producto en el carrito.
    Solo necesita el ID del producto y la cantidad.
    """
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source='product',
        write_only=True
    )

    class Meta:
        model = CartItem
        fields = ['product_id', 'quantity']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser al menos 1.")
        return value

    def validate(self, data):
        product = data['product']
        quantity = data['quantity']
        if quantity > product.stock:
            raise serializers.ValidationError(
                f"No hay suficiente stock para '{product.name}'. Disponible: {product.stock}."
            )
        return data
    

class OrderItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de una orden."""
    # Usamos un serializador más simple para el producto aquí
    product_name = serializers.CharField(source='product.name')

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'quantity', 'price_at_purchase']


class OrderSerializer(serializers.ModelSerializer):
    """Serializador para el historial y detalle de órdenes."""
    items = OrderItemSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email')

    class Meta:
        model = Order
        fields = [
            'id', 'user_email', 'status', 'total_amount', 'delivery_option',
            'delivery_address', 'associated_appointment', 'tracking_number',
            'created_at', 'items'
        ]


class CheckoutSerializer(serializers.Serializer):
    """
    Serializador para validar los datos de entrada en el endpoint de checkout.
    """
    delivery_option = serializers.ChoiceField(choices=Order.DeliveryOptions.choices)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    associated_appointment_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if data['delivery_option'] == Order.DeliveryOptions.DELIVERY and not data.get('delivery_address'):
            raise serializers.ValidationError("La dirección de envío es obligatoria para esta opción de entrega.")
        if data['delivery_option'] == Order.DeliveryOptions.ASSOCIATE_TO_APPOINTMENT and not data.get('associated_appointment_id'):
            raise serializers.ValidationError("Debe seleccionar una cita para asociar la entrega.")
        return data