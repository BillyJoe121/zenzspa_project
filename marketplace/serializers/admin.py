from rest_framework import serializers

from ..models import (
    InventoryMovement,
    Product,
    ProductImage,
    ProductVariant,
    ProductVariantImage,
)
from .shared import ImageUrlMixin


class AdminProductSerializer(serializers.ModelSerializer):
    """CRUD de productos para panel administrativo."""

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "category",
            "preparation_days",
            "what_is_included",
            "benefits",
            "how_to_use",
            "image_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminProductVariantSerializer(serializers.ModelSerializer):
    """Gestiona variantes desde la API administrativa."""

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "name",
            "sku",
            "price",
            "vip_price",
            "stock",
            "reserved_stock",
            "low_stock_threshold",
            "min_order_quantity",
            "max_order_quantity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reserved_stock", "created_at", "updated_at"]


class AdminProductImageSerializer(ImageUrlMixin):
    """Permite gestionar imágenes de productos."""

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "product",
            "image",
            "image_url",
            "url",
            "is_primary",
            "alt_text",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "url", "created_at", "updated_at"]

    def validate(self, data):
        image = data.get("image")
        image_url = data.get("image_url")

        if self.instance:
            if image is None and "image" not in data:
                image = self.instance.image
            if image_url is None and "image_url" not in data:
                image_url = self.instance.image_url

        if not image and not image_url:
            raise serializers.ValidationError(
                "Debes proporcionar una imagen (archivo subido) o una URL de imagen externa."
            )

        return data


class AdminProductVariantImageSerializer(serializers.ModelSerializer):
    """Permite gestionar imágenes de variantes de productos."""

    class Meta:
        model = ProductVariantImage
        fields = [
            "id",
            "variant",
            "image_url",
            "alt_text",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminInventoryMovementSerializer(serializers.ModelSerializer):
    """Serializador para movimientos de inventario manuales."""

    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "variant",
            "quantity",
            "movement_type",
            "reference_order",
            "description",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

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
        movement_type = attrs.get("movement_type")
        quantity = attrs.get("quantity")
        variant = attrs.get("variant") or getattr(self.instance, "variant", None)

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
