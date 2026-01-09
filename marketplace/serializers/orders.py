from rest_framework import serializers

from users.models import CustomUser
from ..models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializador para mostrar los ítems dentro de una orden."""

    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "variant_name", "sku", "quantity", "price_at_purchase"]


class OrderSerializer(serializers.ModelSerializer):
    """Serializador para el historial y detalle de órdenes."""

    items = OrderItemSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source="user.email")

    class Meta:
        model = Order
        fields = [
            "id",
            "user_email",
            "status",
            "total_amount",
            "shipping_cost",
            "delivery_option",
            "delivery_address",
            "associated_appointment",
            "tracking_number",
            "return_reason",
            "return_requested_at",
            "created_at",
            "items",
        ]


class AdminOrderSerializer(serializers.ModelSerializer):
    """Serializer para gestión administrativa de órdenes."""

    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "status",
            "total_amount",
            "shipping_cost",
            "delivery_option",
            "delivery_address",
            "associated_appointment",
            "tracking_number",
            "return_reason",
            "return_requested_at",
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = ["created_at", "updated_at", "return_requested_at"]


class CheckoutSerializer(serializers.Serializer):
    """
    Serializador para validar los datos de entrada en el endpoint de checkout.
    """

    delivery_option = serializers.ChoiceField(choices=Order.DeliveryOptions.choices)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    associated_appointment_id = serializers.UUIDField(required=False)
    use_credits = serializers.BooleanField(required=False, default=False)

    def _validate_delivery_address(self, address):
        import re

        if len(address.strip()) < 10:
            raise serializers.ValidationError(
                {"delivery_address": "La dirección es muy corta. Por favor detalla más la ubicación."}
            )

        address_lower = address.lower()

        if not re.search(r"\d", address):
            raise serializers.ValidationError(
                {"delivery_address": "La dirección debe incluir números (ej: # de casa, calle, apartamento)."}
            )

        invalid_patterns = [
            r"^(test|prueba|ejemplo|xxx)",
            r"^(no tengo|sin direccion|n/a|na|pendiente)",
            r"^(\.)+$",
            r"^(\-)+$",
        ]

        for pattern in invalid_patterns:
            if re.search(pattern, address_lower):
                raise serializers.ValidationError(
                    {"delivery_address": "Por favor ingresa una dirección de envío válida."}
                )

        return address

    def validate(self, data):
        if data["delivery_option"] == Order.DeliveryOptions.DELIVERY:
            address = data.get("delivery_address")
            if not address:
                raise serializers.ValidationError(
                    {"delivery_address": "La dirección de envío es obligatoria para esta opción de entrega."}
                )
            validated_address = self._validate_delivery_address(address)
            data["delivery_address"] = validated_address.strip()

        if data["delivery_option"] == Order.DeliveryOptions.ASSOCIATE_TO_APPOINTMENT and not data.get(
            "associated_appointment_id"
        ):
            raise serializers.ValidationError(
                {"associated_appointment_id": "Debe seleccionar una cita para asociar la entrega."}
            )

        return data


class ReturnItemInputSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnRequestSerializer(serializers.Serializer):
    items = ReturnItemInputSerializer(many=True)
    reason = serializers.CharField()


class ReturnDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
