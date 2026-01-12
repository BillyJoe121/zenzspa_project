import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finances.payments import PaymentService
from legal.models import LegalDocument, UserConsent
from legal.permissions import consent_required_permission
from spa.models import Appointment
from core.utils.decorators import idempotent_view

from ..models import Cart, CartItem, Order
from ..serializers import (
    CartItemCreateUpdateSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
)
from ..services import OrderCreationService

logger = logging.getLogger(__name__)

class CartViewSet(viewsets.GenericViewSet):
    """
    ViewSet para gestionar el carrito de compras del usuario autenticado.
    No es un ModelViewSet completo porque el carrito es un recurso singular.
    """
    permission_classes = [permissions.IsAuthenticated]
    CART_TTL_DAYS = getattr(settings, "CART_TTL_DAYS", 7)

    def get_queryset(self):
        # Este método es necesario para los mixins, aunque no se use directamente.
        return Cart.objects.none()

    def get_cart(self):
        """
        Obtiene o crea el carrito activo, invalidando carritos vencidos.
        """
        now = timezone.now()
        cart = (
            Cart.objects.filter(user=self.request.user, is_active=True)
            .order_by('-created_at')
            .first()
        )
        if cart and cart.expires_at and cart.expires_at < now:
            cart.items.all().delete()
            cart.is_active = False
            cart.save(update_fields=['is_active', 'updated_at'])
            cart = None

        if not cart:
            cart = Cart.objects.create(
                user=self.request.user,
                is_active=True,
                expires_at=now + timedelta(days=self.CART_TTL_DAYS),
            )
        return cart

    def _touch_cart_expiration(self, cart: Cart):
        """Extiende el TTL del carrito en cada interacción."""
        now = timezone.now()
        new_expiry = now + timedelta(days=self.CART_TTL_DAYS)
        if not cart.expires_at or cart.expires_at < new_expiry:
            cart.expires_at = new_expiry
            cart.save(update_fields=['expires_at', 'updated_at'])
        return cart

    @action(detail=False, methods=['get'], url_path='my-cart')
    def my_cart(self, request):
        """
        Obtiene el contenido del carrito de compras del usuario actual.
        GET /api/v1/marketplace/cart/my-cart/
        """
        cart = self.get_cart()
        serializer = CartSerializer(
            cart,
            context={'request': request, 'view': self}
        )
        return Response(serializer.data)


    @action(detail=False, methods=['post'], url_path='add-item')
    @idempotent_view(timeout=5)
    @transaction.atomic
    def add_item(self, request):
        """
        Añade una variante al carrito o actualiza su cantidad si ya existe.
        POST /api/v1/marketplace/cart/add-item/
        Body: { "variant_id": "uuid", "quantity": 1 } o { "sku": "ABC123", "quantity": 1 }
        """
        MAX_CART_ITEMS = 50
        MAX_ITEM_QUANTITY = 100

        cart = self.get_cart()
        self._touch_cart_expiration(cart)
        
        if cart.items.count() >= MAX_CART_ITEMS:
            return Response(
                {
                    "error": f"Has alcanzado el límite de {MAX_CART_ITEMS} productos diferentes en el carrito.",
                    "code": "MKT-CART-LIMIT"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CartItemCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        variant_input = serializer.validated_data['variant']
        quantity = serializer.validated_data['quantity']

        if quantity > MAX_ITEM_QUANTITY:
            return Response(
                {
                    "error": f"La cantidad máxima por producto es {MAX_ITEM_QUANTITY}.",
                    "code": "MKT-QUANTITY-LIMIT"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Lock variant para evitar race condition y asegurar lectura fresca de stock
        # Nota: variant_input viene del serializer, necesitamos re-consultar con lock
        from ..models import ProductVariant
        variant = ProductVariant.objects.select_for_update().get(pk=variant_input.pk)

        # Buscamos si el ítem ya existe en el carrito para actualizarlo
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=variant,
            defaults={'quantity': quantity}
        )

        if not created:
            new_quantity = cart_item.quantity + quantity
        else:
            new_quantity = quantity
            
        if new_quantity > MAX_ITEM_QUANTITY:
             return Response(
                {
                    "error": f"La cantidad total del producto excede el límite de {MAX_ITEM_QUANTITY}.",
                    "code": "MKT-QUANTITY-LIMIT"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar contra stock disponible (stock - reserved_stock)
        available = variant.stock - variant.reserved_stock
        if new_quantity > available:
             return Response(
                {
                    "error": f"Stock insuficiente. Disponible: {available}, solicitado: {new_quantity}.",
                    "code": "MKT-STOCK-CART"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not created:
            cart_item.quantity = new_quantity
            cart_item.save()
        # Devolvemos el contenido completo del carrito actualizado
        cart_serializer = CartSerializer(cart, context={'request': request, 'view': self})
        return Response(cart_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'], url_path='update-item')
    def update_cart_item(self, request, pk=None):
        """
        Actualiza la cantidad de un ítem específico en el carrito.
        PUT /api/v1/marketplace/cart/{cart_item_id}/update-item/
        Body: { "quantity": 3 }
        """
        try:
            cart_item = CartItem.objects.get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response({"error": "Ítem de carrito no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Usamos partial=True para permitir actualizar solo la cantidad
        serializer = CartItemCreateUpdateSerializer(cart_item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        cart_serializer = CartSerializer(self.get_cart(), context={'request': request, 'view': self})
        self._touch_cart_expiration(cart_item.cart)
        return Response(cart_serializer.data)

    @action(detail=True, methods=['delete'], url_path='remove-item')
    def remove_cart_item(self, request, pk=None):
        """
        Elimina un ítem específico del carrito.
        DELETE /api/v1/marketplace/cart/{cart_item_id}/remove-item/
        """
        try:
            cart_item = CartItem.objects.get(pk=pk, cart__user=request.user)
            cart = cart_item.cart
            cart_item.delete()
            self._touch_cart_expiration(cart)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CartItem.DoesNotExist:
            return Response({"error": "Ítem de carrito no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
    @action(
        detail=False,
        methods=['post'],
        url_path='checkout',
        permission_classes=[
            permissions.IsAuthenticated,
            consent_required_permission(
                LegalDocument.DocumentType.PURCHASE,
                context_type=UserConsent.ContextType.ORDER,
            ),
        ],
    )
    @idempotent_view(timeout=60)
    def checkout(self, request):
        """
        Crea una orden a partir del carrito y la prepara para el pago.
        """
        cart = self.get_cart()
        
        # 1. Validar los datos de entrada para el checkout
        checkout_serializer = CheckoutSerializer(data=request.data)
        checkout_serializer.is_valid(raise_exception=True)
        validated_data = checkout_serializer.validated_data
        
        # Opcional: Validar que la cita asociada exista y pertenezca al usuario
        if 'associated_appointment_id' in validated_data:
            try:
                appointment = Appointment.objects.get(
                    id=validated_data['associated_appointment_id'], 
                    user=request.user
                )
                validated_data['associated_appointment'] = appointment
            except Appointment.DoesNotExist:
                return Response({"error": "La cita asociada no es válida."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Usar el servicio para crear la orden
        try:
            order_service = OrderCreationService(
                user=request.user,
                cart=cart,
                data=validated_data
            )
            order = order_service.create_order()

            # Crear registro de pago y obtener payload para Wompi usando servicio centralizado
            # Extraer el parámetro use_credits del request validado
            use_credits = validated_data.get('use_credits', False)

            try:
                payment, payment_payload = PaymentService.create_order_payment(
                    request.user,
                    order,
                    use_credits=use_credits
                )
            except ValueError as e:
                logger.error("Error al iniciar pago de orden %s: %s", order.id, e)
                from ..services import OrderService
                OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
                return Response(
                    {"error": str(e), "code": "MKT-PAYMENT-ERROR"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            order_serializer = OrderSerializer(order)
            response_data = {
                'order': order_serializer.data,
                'payment': payment_payload,
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

