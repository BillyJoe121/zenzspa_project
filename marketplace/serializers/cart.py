from decimal import Decimal

from rest_framework import serializers

from ..models import Cart, CartItem, ProductVariant
from .catalog import ProductVariantSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de un carrito."""

    variant = ProductVariantSerializer(read_only=True)
    product = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "variant", "quantity", "subtotal"]

    def get_product(self, obj):
        product = obj.variant.product
        return {
            "id": product.id,
            "name": product.name,
        }

    def get_subtotal(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
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
        fields = ["id", "user", "is_active", "items", "total"]

    def get_total(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        total = Decimal("0")
        for item in obj.items.select_related("variant"):
            price = item.variant.price
            if user and getattr(user, "is_vip", False) and item.variant.vip_price:
                price = item.variant.vip_price
            total += price * item.quantity
        return total


class CartItemCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para añadir o actualizar una variante en el carrito.
    Soporta tanto variant_id como sku.
    """

    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.select_related("product").filter(product__is_active=True),
        source="variant",
        write_only=True,
        required=False,
    )
    sku = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CartItem
        fields = ["variant_id", "sku", "quantity"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser al menos 1.")
        return value

    def validate(self, data):
        sku = data.pop("sku", None)
        variant = data.get("variant")
        instance = getattr(self, "instance", None)

        if sku and variant:
            raise serializers.ValidationError("Envía solo variant_id o sku, no ambos.")

        if not variant and sku:
            try:
                variant = ProductVariant.objects.select_related("product").get(
                    sku=sku,
                    product__is_active=True,
                )
            except ProductVariant.DoesNotExist:
                raise serializers.ValidationError("SKU inválido o producto inactivo.")
            data["variant"] = variant
        elif not variant and instance:
            variant = instance.variant

        if not variant:
            raise serializers.ValidationError("Debes especificar una variante válida.")

        if not variant.product.is_active:
            raise serializers.ValidationError("El producto asociado está inactivo.")

        quantity = data.get("quantity")
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
