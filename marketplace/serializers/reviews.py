from rest_framework import serializers

from ..models import Order, ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    """
    Serializador para mostrar reseñas de productos.
    """

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "product",
            "user_name",
            "user_email",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "is_approved",
            "admin_response",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "user_name",
            "user_email",
            "is_verified_purchase",
            "is_approved",
            "created_at",
            "updated_at",
        ]


class ProductReviewCreateSerializer(serializers.ModelSerializer):
    """
    Serializador para crear reseñas de productos.
    """

    order_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = ProductReview
        fields = ["product", "rating", "title", "comment", "order_id"]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("La calificación debe estar entre 1 y 5.")
        return value

    def validate(self, data):
        user = self.context["request"].user
        product = data.get("product")

        if ProductReview.objects.filter(product=product, user=user).exists():
            raise serializers.ValidationError(
                "Ya has dejado una reseña para este producto. Puedes editarla o eliminarla."
            )

        if not data.get("title") and not data.get("comment"):
            raise serializers.ValidationError("Debes proporcionar al menos un título o un comentario.")

        order_id = data.pop("order_id", None)
        if order_id:
            try:
                order = Order.objects.get(id=order_id, user=user)
                if not order.items.filter(variant__product=product).exists():
                    raise serializers.ValidationError("El producto no está en la orden especificada.")
                if order.status != Order.OrderStatus.DELIVERED:
                    raise serializers.ValidationError(
                        "Solo puedes dejar reseñas verificadas para productos de órdenes entregadas."
                    )
                data["order"] = order
            except Order.DoesNotExist:
                raise serializers.ValidationError("La orden especificada no existe o no te pertenece.")

        return data

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class ProductReviewUpdateSerializer(serializers.ModelSerializer):
    """
    Serializador para actualizar reseñas existentes.
    """

    class Meta:
        model = ProductReview
        fields = ["rating", "title", "comment"]

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
