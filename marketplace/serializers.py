from decimal import Decimal

from rest_framework import serializers

from users.models import CustomUser
from .models import (
    Product,
    ProductCategory,
    ProductImage,
    ProductVariant,
    Cart,
    CartItem,
    Order,
    OrderItem,
    ProductReview,
    InventoryMovement,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    """Serializador para categorías de productos del marketplace."""
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'description', 'product_count']
        read_only_fields = ['id', 'product_count']

    def get_product_count(self, obj):
        """Cuenta productos activos en esta categoría."""
        return obj.products.filter(is_active=True).count()




def _show_sensitive_data(context):
    """Determina si el usuario autenticado puede ver campos sensibles."""
    request = context.get('request') if context else None
    user = getattr(request, 'user', None)
    return bool(user and getattr(user, 'is_authenticated', False))

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Solo ocultar stock para usuarios no autenticados
        # vip_price siempre debe ser visible (es información de marketing)
        if not _show_sensitive_data(self.context):
            data.pop('stock', None)
        return data


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
        fields = ['id', 'name', 'price', 'vip_price', 'stock', 'main_image', 'category']

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
        # vip_price siempre visible (información de marketing)
        return self._get_price_candidate(obj, 'vip_price')

    def get_stock(self, obj):
        if not _show_sensitive_data(self.context):
            return None
        return sum(variant.stock for variant in obj.variants.all())

class ProductDetailSerializer(ProductListSerializer):
    """
    Serializador para ver el detalle de un solo producto.
    Muestra todas las imágenes y la descripción completa.
    """
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'description',
            'preparation_days',
            'images',
            'variants',
            'average_rating',
            'review_count',
            'what_is_included',
            'benefits',
            'how_to_use',
        ]

    def get_average_rating(self, obj):
        """Calcula el promedio de calificaciones aprobadas."""
        from django.db.models import Avg
        result = obj.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))
        avg = result['avg']
        return round(avg, 2) if avg else None

    def get_review_count(self, obj):
        """Cuenta las reseñas aprobadas."""
        return obj.reviews.filter(is_approved=True).count()

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

        available = variant.stock - variant.reserved_stock
        if quantity and quantity > available:
            raise serializers.ValidationError(
                f"No hay suficiente stock para '{variant}'. Disponible: {available}."
            )
        
        if quantity and variant.min_order_quantity and quantity < variant.min_order_quantity:
            raise serializers.ValidationError(
                f"La cantidad mínima para '{variant}' es {variant.min_order_quantity}."
            )

        if quantity and variant.max_order_quantity and quantity > variant.max_order_quantity:
            raise serializers.ValidationError(
                f"La cantidad máxima para '{variant}' es {variant.max_order_quantity}."
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
            'id', 'user_email', 'status', 'total_amount', 'shipping_cost',
            'delivery_option', 'delivery_address', 'associated_appointment',
            'tracking_number', 'return_reason', 'return_requested_at',
            'created_at', 'items'
        ]


class AdminOrderSerializer(serializers.ModelSerializer):
    """Serializer para gestión administrativa de órdenes."""
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())

    class Meta:
        model = Order
        fields = [
            'id',
            'user',
            'status',
            'total_amount',
            'shipping_cost',
            'delivery_option',
            'delivery_address',
            'associated_appointment',
            'tracking_number',
            'return_reason',
            'return_requested_at',
            'created_at',
            'updated_at',
            'items',
        ]
        read_only_fields = ['created_at', 'updated_at', 'return_requested_at']


class CheckoutSerializer(serializers.Serializer):
    """
    Serializador para validar los datos de entrada en el endpoint de checkout.
    """
    delivery_option = serializers.ChoiceField(choices=Order.DeliveryOptions.choices)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    associated_appointment_id = serializers.UUIDField(required=False)
    use_credits = serializers.BooleanField(required=False, default=False)

    def _validate_delivery_address(self, address):
        """
        Valida la dirección de envío de manera flexible.
        Se busca asegurar que sea una dirección real pero sin bloquear formatos válidos.
        """
        import re

        # Validación 1: Longitud mínima (reducida para ser más flexible)
        if len(address.strip()) < 10:
            raise serializers.ValidationError({
                "delivery_address": "La dirección es muy corta. Por favor detalla más la ubicación."
            })

        address_lower = address.lower()

        # Validación 2: Debe contener números (para la nomenclatura o identificación de casa)
        if not re.search(r'\d', address):
            raise serializers.ValidationError({
                "delivery_address": "La dirección debe incluir números (ej: # de casa, calle, apartamento)."
            })

        # Validación 3: Verificar que no sea una dirección "basura" común
        invalid_patterns = [
            r'^(test|prueba|ejemplo|xxx)', 
            r'^(no tengo|sin direccion|n/a|na|pendiente)',
            r'^(\.)+$', # Solo puntos
            r'^(\-)+$', # Solo guiones
        ]

        for pattern in invalid_patterns:
            if re.search(pattern, address_lower):
                raise serializers.ValidationError({
                    "delivery_address": "Por favor ingresa una dirección de envío válida."
                })

        # Advertencias (no bloqueantes)
        # Si no detectamos palabras clave de vía comunes, solo sugerimos (opcional en frontend, aquí pasa)
        via_types = [
            'calle', 'carrera', 'avenida', 'transversal', 'diagonal',
            'circular', 'autopista', 'manzana', 'vereda', 'kilometro',
            'cra', 'cll', 'av', 'trans', 'diag', 'circ', 'km', '#', 'no'
        ]
        
        # Simplemente retornamos limpia la dirección
        return address

    def validate(self, data):
        if data['delivery_option'] == Order.DeliveryOptions.DELIVERY:
            address = data.get('delivery_address')
            if not address:
                raise serializers.ValidationError({
                    "delivery_address": "La dirección de envío es obligatoria para esta opción de entrega."
                })

            # Usar validación exhaustiva
            validated_address = self._validate_delivery_address(address)
            data['delivery_address'] = validated_address.strip()

        if data['delivery_option'] == Order.DeliveryOptions.ASSOCIATE_TO_APPOINTMENT and not data.get('associated_appointment_id'):
            raise serializers.ValidationError({
                "associated_appointment_id": "Debe seleccionar una cita para asociar la entrega."
            })

        return data


class ReturnItemInputSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnRequestSerializer(serializers.Serializer):
    items = ReturnItemInputSerializer(many=True)
    reason = serializers.CharField()


class ReturnDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()


# --- Serializadores de Reviews ---

class ProductReviewSerializer(serializers.ModelSerializer):
    """
    Serializador para mostrar reseñas de productos.
    """
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            'id',
            'product',
            'user_name',
            'user_email',
            'rating',
            'title',
            'comment',
            'is_verified_purchase',
            'is_approved',
            'admin_response',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['user_name', 'user_email', 'is_verified_purchase', 'is_approved', 'created_at', 'updated_at']


class ProductReviewCreateSerializer(serializers.ModelSerializer):
    """
    Serializador para crear reseñas de productos.
    """
    order_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = ProductReview
        fields = ['product', 'rating', 'title', 'comment', 'order_id']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("La calificación debe estar entre 1 y 5.")
        return value

    def validate(self, data):
        user = self.context['request'].user
        product = data.get('product')

        # Verificar que el usuario no haya dejado ya una reseña para este producto
        if ProductReview.objects.filter(product=product, user=user).exists():
            raise serializers.ValidationError(
                "Ya has dejado una reseña para este producto. Puedes editarla o eliminarla."
            )

        # Validar que al menos haya título o comentario
        if not data.get('title') and not data.get('comment'):
            raise serializers.ValidationError(
                "Debes proporcionar al menos un título o un comentario."
            )

        # Si se proporciona order_id, validar que exista y pertenezca al usuario
        order_id = data.pop('order_id', None)
        if order_id:
            try:
                order = Order.objects.get(id=order_id, user=user)
                # Verificar que la orden contenga el producto
                if not order.items.filter(variant__product=product).exists():
                    raise serializers.ValidationError(
                        "El producto no está en la orden especificada."
                    )
                # Verificar que la orden esté entregada
                if order.status != Order.OrderStatus.DELIVERED:
                    raise serializers.ValidationError(
                        "Solo puedes dejar reseñas verificadas para productos de órdenes entregadas."
                    )
                data['order'] = order
            except Order.DoesNotExist:
                raise serializers.ValidationError("La orden especificada no existe o no te pertenece.")

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ProductReviewUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para actualizar reseñas existentes.
    """
    class Meta:
        model = ProductReview
        fields = ['rating', 'title', 'comment']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("La calificación debe estar entre 1 y 5.")
        return value


class AdminReviewResponseSerializer(serializers.Serializer):
    """
    Serializador para que los administradores respondan a reseñas.
    """
    admin_response = serializers.CharField(required=True, allow_blank=False)
    is_approved = serializers.BooleanField(required=False)


# --- Serializadores Administrativos del Marketplace ---

class AdminProductSerializer(serializers.ModelSerializer):
    """CRUD de productos para panel administrativo."""

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'description',
            'is_active',
            'category',
            'preparation_days',
            'what_is_included',
            'benefits',
            'how_to_use',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AdminProductVariantSerializer(serializers.ModelSerializer):
    """Gestiona variantes desde la API administrativa."""

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'product',
            'name',
            'sku',
            'price',
            'vip_price',
            'stock',
            'reserved_stock',
            'low_stock_threshold',
            'min_order_quantity',
            'max_order_quantity',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reserved_stock', 'created_at', 'updated_at']


class AdminProductImageSerializer(serializers.ModelSerializer):
    """Permite gestionar imágenes de productos."""

    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'image', 'is_primary', 'alt_text', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AdminInventoryMovementSerializer(serializers.ModelSerializer):
    """Serializador para movimientos de inventario manuales."""
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = InventoryMovement
        fields = [
            'id',
            'variant',
            'quantity',
            'movement_type',
            'reference_order',
            'description',
            'created_by',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']

    @staticmethod
    def compute_deltas(movement_type, quantity):
        """Retorna (delta_stock, delta_reserved)."""
        if movement_type in {
            InventoryMovement.MovementType.RESTOCK,
            InventoryMovement.MovementType.RETURN,
        }:
            return quantity, 0
        if movement_type == InventoryMovement.MovementType.SALE:
            return -quantity, 0
        if movement_type == InventoryMovement.MovementType.ADJUSTMENT:
            return quantity, 0
        if movement_type == InventoryMovement.MovementType.RESERVATION:
            return 0, quantity
        if movement_type in {
            InventoryMovement.MovementType.RESERVATION_RELEASE,
            InventoryMovement.MovementType.EXPIRED_RESERVATION,
        }:
            return 0, -quantity
        return 0, 0

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("La cantidad no puede ser cero.")
        return value

    def validate(self, attrs):
        movement_type = attrs.get('movement_type')
        quantity = attrs.get('quantity')
        variant = attrs.get('variant') or getattr(self.instance, 'variant', None)

        positive_only = {
            InventoryMovement.MovementType.SALE,
            InventoryMovement.MovementType.RETURN,
            InventoryMovement.MovementType.RESERVATION,
            InventoryMovement.MovementType.RESERVATION_RELEASE,
            InventoryMovement.MovementType.RESTOCK,
            InventoryMovement.MovementType.EXPIRED_RESERVATION,
        }
        if movement_type in positive_only and quantity < 0:
            raise serializers.ValidationError("La cantidad debe ser positiva para este tipo de movimiento.")

        delta_stock, delta_reserved = self.compute_deltas(movement_type, quantity)

        if not variant:
            return attrs

        if delta_stock and variant.stock + delta_stock < 0:
            raise serializers.ValidationError("El stock no puede quedar negativo.")

        if delta_reserved and variant.reserved_stock + delta_reserved < 0:
            raise serializers.ValidationError("El stock reservado no puede quedar negativo.")

        return attrs
