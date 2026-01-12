from decimal import Decimal

from rest_framework import serializers

from ..models import Product, ProductCategory, ProductImage, ProductVariant, ProductVariantImage
from .shared import _show_sensitive_data, ImageUrlMixin


class ProductCategorySerializer(serializers.ModelSerializer):
    """Serializador para categorías de productos del marketplace."""

    product_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "description", "product_count"]
        read_only_fields = ["id", "product_count"]

    def get_product_count(self, obj):
        """Cuenta productos activos en esta categoría."""
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(ImageUrlMixin):
    """Serializador para las imágenes de un producto."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "image_url", "url", "is_primary", "alt_text", "display_order"]


class ProductVariantImageSerializer(serializers.ModelSerializer):
    """Serializador para las imágenes de una variante."""

    class Meta:
        model = ProductVariantImage
        fields = ["id", "image_url", "alt_text", "display_order"]


class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializador para variantes individuales."""

    images = ProductVariantImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "sku", "name", "price", "vip_price", "stock", "images"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _show_sensitive_data(self.context):
            data.pop("stock", None)
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
        fields = ["id", "name", "price", "vip_price", "stock", "main_image", "category", "image_url"]

    def get_main_image(self, obj):
        primary_image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if primary_image:
            return ProductImageSerializer(primary_image).data
        return None

    def _get_price_candidate(self, obj, attr):
        candidates = [getattr(variant, attr) for variant in obj.variants.all() if getattr(variant, attr) is not None]
        return min(candidates) if candidates else None

    def get_price(self, obj):
        return self._get_price_candidate(obj, "price")

    def get_vip_price(self, obj):
        return self._get_price_candidate(obj, "vip_price")

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
            "description",
            "preparation_days",
            "images",
            "variants",
            "average_rating",
            "review_count",
            "what_is_included",
            "benefits",
            "how_to_use",
            "image_url",
        ]

    def get_average_rating(self, obj):
        from django.db.models import Avg

        result = obj.reviews.filter(is_approved=True).aggregate(avg=Avg("rating"))
        avg = result["avg"]
        return round(avg, 2) if avg else None

    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()
