# marketplace/views.py

from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from spa.models import Appointment
from users.models import CustomUser
from core.decorators import idempotent_view

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
        cart = self.get_cart()
        serializer = CartSerializer(cart, context={'request': request, 'view': self})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='add-item')
    def add_item(self, request):
        """
        Añade una variante al carrito o actualiza su cantidad si ya existe.
        POST /api/v1/marketplace/cart/add-item/
        Body: { "variant_id": "uuid", "quantity": 1 } o { "sku": "ABC123", "quantity": 1 }
        """
        cart = self.get_cart()
        serializer = CartItemCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        variant = serializer.validated_data['variant']
        quantity = serializer.validated_data['quantity']

        # Buscamos si el ítem ya existe en el carrito para actualizarlo
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=variant,
            defaults={'quantity': quantity}
        )

        if not created:
            # Si ya existía, actualizamos la cantidad
            cart_item.quantity += quantity
            # Validar stock total
            if cart_item.quantity > variant.stock:
                 return Response(
                    {"error": f"No hay suficiente stock para '{variant}'. Disponible: {variant.stock}."},
                    status=status.HTTP_400_BAD_REQUEST
                )
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
            
            # 3. Preparar la respuesta
            order_serializer = OrderSerializer(order)
            response_data = order_serializer.data
            response_data['wompi_reference'] = order.wompi_transaction_id
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
        permission_classes=[permissions.IsAdminUser],
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

