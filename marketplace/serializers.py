from decimal import Decimal

from rest_framework import serializers

from .models import (
    Product,
    ProductImage,
    ProductVariant,
    Cart,
    CartItem,
    Order,
    OrderItem,
)

# --- Serializadores de Lectura (Para mostrar datos) ---

class ProductImageSerializer(serializers.ModelSerializer):
    """Serializador para las imágenes de un producto."""
    class Meta:
        model = ProductImage
        fields = ['image', 'is_primary', 'alt_text']

class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializador para variantes individuales."""

    class Meta:
        model = ProductVariant
        fields = ['id', 'sku', 'name', 'price', 'vip_price', 'stock']


class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializador para listar productos en el catálogo.
    Muestra solo la imagen principal para mantener la respuesta ligera.
    """
    main_image = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    vip_price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()

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

    def _get_price_candidate(self, obj, attr):
        candidates = [
            getattr(variant, attr)
            for variant in obj.variants.all()
            if getattr(variant, attr) is not None
        ]
        return min(candidates) if candidates else None

    def get_price(self, obj):
        return self._get_price_candidate(obj, 'price')

    def get_vip_price(self, obj):
        return self._get_price_candidate(obj, 'vip_price')

    def get_stock(self, obj):
        return sum(variant.stock for variant in obj.variants.all())

class ProductDetailSerializer(ProductListSerializer):
    """
    Serializador para ver el detalle de un solo producto.
    Muestra todas las imágenes y la descripción completa.
    """
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'description',
            'category',
            'preparation_days',
            'images',
            'variants',
        ]

class CartItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de un carrito."""
    variant = ProductVariantSerializer(read_only=True)
    product = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'variant', 'quantity', 'subtotal']

    def get_product(self, obj):
        product = obj.variant.product
        return {
            'id': product.id,
            'name': product.name,
        }

    def get_subtotal(self, obj):
        # Calcula el subtotal basado en el rol del usuario que ve el carrito
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        price = obj.variant.price
        if user and getattr(user, "is_vip", False) and obj.variant.vip_price:
            price = obj.variant.vip_price
        return obj.quantity * price

class CartSerializer(serializers.ModelSerializer):
    """Serializador para mostrar el contenido completo del carrito de un usuario."""
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'is_active', 'items', 'total']
    
    def get_total(self, obj):
        # Calcula el total aplicando el precio VIP si corresponde.
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        total = Decimal('0')
        for item in obj.items.select_related('variant'):
            price = item.variant.price
            if user and getattr(user, "is_vip", False) and item.variant.vip_price:
                price = item.variant.vip_price
            total += price * item.quantity
        return total

# --- Serializadores de Escritura (Para crear/actualizar datos) ---

class CartItemCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para añadir o actualizar una variante en el carrito.
    Soporta tanto variant_id como sku.
    """
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related('product').filter(product__is_active=True),
        source='variant',
        write_only=True,
        required=False,
    )
    sku = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CartItem
        fields = ['variant_id', 'sku', 'quantity']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser al menos 1.")
        return value

    def validate(self, data):
        sku = data.pop('sku', None)
        variant = data.get('variant')
        instance = getattr(self, 'instance', None)

        if sku and variant:
            raise serializers.ValidationError("Envía solo variant_id o sku, no ambos.")

        if not variant and sku:
            try:
                variant = ProductVariant.objects.select_related('product').get(
                    sku=sku,
                    product__is_active=True,
                )
            except ProductVariant.DoesNotExist:
                raise serializers.ValidationError("SKU inválido o producto inactivo.")
            data['variant'] = variant
        elif not variant and instance:
            variant = instance.variant

        if not variant:
            raise serializers.ValidationError("Debes especificar una variante válida.")

        if not variant.product.is_active:
            raise serializers.ValidationError("El producto asociado está inactivo.")

        quantity = data.get('quantity')
        if quantity is None and instance:
            quantity = instance.quantity

        if quantity and quantity > variant.stock:
            raise serializers.ValidationError(
                f"No hay suficiente stock para '{variant}'. Disponible: {variant.stock}."
            )

        return data

class OrderItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de una orden."""
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    variant_name = serializers.CharField(source='variant.name', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'variant_name', 'sku', 'quantity', 'price_at_purchase']


class OrderSerializer(serializers.ModelSerializer):
    """Serializador para el historial y detalle de órdenes."""
    items = OrderItemSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email')

    class Meta:
        model = Order
        fields = [
            'id', 'user_email', 'status', 'total_amount', 'delivery_option',
            'delivery_address', 'associated_appointment', 'tracking_number',
            'return_reason', 'return_requested_at',
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


class ReturnItemInputSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnRequestSerializer(serializers.Serializer):
    items = ReturnItemInputSerializer(many=True)
    reason = serializers.CharField()


class ReturnDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
