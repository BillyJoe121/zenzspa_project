# marketplace/views.py
import uuid

from django.conf import settings
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from spa.models import Appointment, Payment
from spa.services import PaymentService
from users.models import CustomUser
from users.permissions import IsAdminUser as DomainIsAdminUser
from core.decorators import idempotent_view
from django.db import transaction
import requests
import logging

logger = logging.getLogger(__name__)

from .models import Product, Cart, CartItem, Order
from .serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductVariantSerializer,
    CartSerializer,
    CartItemCreateUpdateSerializer,
    OrderSerializer,
    CheckoutSerializer,
    ReturnRequestSerializer,
    ReturnDecisionSerializer,
)
from .services import OrderCreationService, ReturnService

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para ver el catálogo de productos.
    Permite listar todos los productos activos y ver el detalle de uno solo.
    """
    permission_classes = [permissions.AllowAny]
    queryset = (
        Product.objects.filter(is_active=True)
        .prefetch_related('images', 'variants')
    )

    def get_serializer_class(self):
        """
        Devuelve un serializador diferente para la vista de lista y la de detalle,
        como lo diseñamos previamente.
        """
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=True, methods=['get'])
    def variants(self, request, pk=None):
        """
        Lista las variantes del producto solicitado.
        GET /api/v1/products/{id}/variants/
        """
        product = self.get_object()
        serializer = ProductVariantSerializer(product.variants.all(), many=True)
        return Response(serializer.data)

class CartViewSet(viewsets.GenericViewSet):
    """
    ViewSet para gestionar el carrito de compras del usuario autenticado.
    No es un ModelViewSet completo porque el carrito es un recurso singular.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Este método es necesario para los mixins, aunque no se use directamente.
        return Cart.objects.none()

    def get_cart(self):
        """
        Método de ayuda para obtener o crear el carrito activo del usuario.
        """
        cart, _ = Cart.objects.get_or_create(user=self.request.user, is_active=True)
        return cart

    @action(detail=False, methods=['get'], url_path='my-cart')
    def my_cart(self, request):
        """
        Obtiene el contenido del carrito de compras del usuario actual.
        GET /api/v1/marketplace/cart/my-cart/
        """


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
        from .models import ProductVariant
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
        return Response(cart_serializer.data)

    @action(detail=True, methods=['delete'], url_path='remove-item')
    def remove_cart_item(self, request, pk=None):
        """
        Elimina un ítem específico del carrito.
        DELETE /api/v1/marketplace/cart/{cart_item_id}/remove-item/
        """
        try:
            cart_item = CartItem.objects.get(pk=pk, cart__user=request.user)
            cart_item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CartItem.DoesNotExist:
            return Response({"error": "Ítem de carrito no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
    @action(detail=False, methods=['post'], url_path='checkout')
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

            # Crear registro de pago asociado a la orden
            reference = f"ORDER-{order.id}-{uuid.uuid4().hex[:8]}"
            payment = Payment.objects.create(
                user=request.user,
                amount=order.total_amount,
                status=Payment.PaymentStatus.PENDING,
                payment_type=Payment.PaymentType.ORDER,
                transaction_id=reference,
                order=order,
            )
            order.wompi_transaction_id = reference
            order.save(update_fields=['wompi_transaction_id', 'updated_at'])

            amount_in_cents = int(order.total_amount * 100)
            base_url = getattr(settings, "WOMPI_BASE_URL", PaymentService.WOMPI_DEFAULT_BASE_URL)
            
            try:
                acceptance_token = PaymentService._resolve_acceptance_token(base_url)
            except requests.Timeout:
                logger.error("Timeout al obtener acceptance token de Wompi")
                # Cancelar orden para no dejarla en limbo si no se puede pagar
                from .services import OrderService
                OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
                return Response(
                    {"error": "El servicio de pagos no está disponible. Intenta más tarde.", "code": "MKT-PAYMENT-UNAVAILABLE"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            except requests.RequestException as e:
                logger.exception("Error al comunicarse con Wompi: %s", e)
                from .services import OrderService
                OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
                return Response(
                    {"error": "Error al procesar el pago. Intenta más tarde.", "code": "MKT-PAYMENT-ERROR"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            signature = PaymentService._build_integrity_signature(
                reference=reference,
                amount_in_cents=amount_in_cents,
                currency=getattr(settings, "WOMPI_CURRENCY", "COP"),
            )

            payment_payload = {
                'publicKey': settings.WOMPI_PUBLIC_KEY,
                'currency': getattr(settings, "WOMPI_CURRENCY", "COP"),
                'amountInCents': amount_in_cents,
                'reference': reference,
                'signature:integrity': signature,
                'redirectUrl': settings.WOMPI_REDIRECT_URL,
                'acceptanceToken': acceptance_token,
                'paymentId': str(payment.id),
            }

            order_serializer = OrderSerializer(order)
            response_data = {
                'order': order_serializer.data,
                'payment': payment_payload,
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet de solo lectura para que un usuario pueda ver su historial de órdenes.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        """Asegura que cada usuario solo pueda ver sus propias órdenes."""
        queryset = Order.objects.prefetch_related('items__variant__product')
        user = self.request.user
        if getattr(user, 'role', None) in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return queryset
        return queryset.filter(user=user)

    @action(detail=True, methods=['post'], url_path='request-return')
    def request_return(self, request, pk=None):
        order = self.get_object()
        if order.user != request.user:
            return Response(
                {"detail": "Solo el dueño de la orden puede solicitar devoluciones."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReturnRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated_order = ReturnService.request_return(
                order,
                serializer.validated_data['items'],
                serializer.validated_data['reason'],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(updated_order).data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='process-return',
        permission_classes=[DomainIsAdminUser],
    )
    def process_return(self, request, pk=None):
        order = self.get_object()
        serializer = ReturnDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated_order = ReturnService.process_return(
                order,
                approved=serializer.validated_data['approved'],
                processed_by=request.user,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(updated_order).data, status=status.HTTP_200_OK)

