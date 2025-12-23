# marketplace/views.py
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import timedelta

from spa.models import Appointment
from legal.models import LegalDocument, UserConsent
from legal.permissions import consent_required_permission
from finances.payments import PaymentService
from users.models import CustomUser
from users.permissions import (
    IsAdminUser as DomainIsAdminUser,
    IsStaffOrAdmin as DomainIsStaffOrAdmin,
)
from core.decorators import idempotent_view
import logging

logger = logging.getLogger(__name__)

from .models import (
    Cart,
    CartItem,
    InventoryMovement,
    Order,
    Product,
    ProductCategory,
    ProductImage,
    ProductReview,
    ProductVariant,
)
from .serializers import (
    ProductCategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductVariantSerializer,
    CartSerializer,
    CartItemCreateUpdateSerializer,
    OrderSerializer,
    CheckoutSerializer,
    ReturnRequestSerializer,
    ReturnDecisionSerializer,
    ProductReviewSerializer,
    ProductReviewCreateSerializer,
    ProductReviewUpdateSerializer,
    AdminReviewResponseSerializer,
    AdminInventoryMovementSerializer,
    AdminProductImageSerializer,
    AdminProductSerializer,
    AdminProductVariantSerializer,
    AdminOrderSerializer,
)
from .services import OrderCreationService, ReturnService


class ProductCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de categorías de productos del marketplace.

    - LIST/RETRIEVE: Cualquier usuario autenticado
    - CREATE/UPDATE/DELETE: Solo ADMIN
    """
    queryset = ProductCategory.objects.all().order_by('name')
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    
    def get_permissions(self):
        """Solo ADMIN puede crear, actualizar o eliminar categorías."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [DomainIsAdminUser()]
        return super().get_permissions()
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete de la categoría.
        Verifica que no tenga productos activos asociados.
        """
        instance = self.get_object()
        
        active_products = instance.products.filter(is_active=True).count()
        if active_products > 0:
            return Response(
                {
                    'error': f'No se puede eliminar la categoría porque tiene {active_products} producto(s) activo(s) asociado(s).'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete
        instance.deleted_at = timezone.now()
        instance.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)



class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para ver el catálogo de productos.
    Permite listar todos los productos activos y ver el detalle de uno solo.

    Búsqueda disponible:
    - ?search=término : Busca en nombre y descripción del producto
    - ?category=uuid : Filtra por categoría
    - ?min_price=100 : Precio mínimo
    - ?max_price=500 : Precio máximo
    - ?in_stock=true : Solo productos con stock disponible
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
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

    def get_queryset(self):
        """
        Filtra productos según parámetros de búsqueda.
        """
        queryset = super().get_queryset()

        # Búsqueda por texto en nombre y descripción
        search = self.request.query_params.get('search', None)
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # Filtro por categoría
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category_id=category)

        # Filtro por rango de precio
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)

        if min_price or max_price:
            # Filtrar productos que tengan al menos una variante en el rango
            from django.db.models import Min
            queryset = queryset.annotate(lowest_price=Min('variants__price'))

            if min_price:
                queryset = queryset.filter(lowest_price__gte=min_price)
            if max_price:
                queryset = queryset.filter(lowest_price__lte=max_price)

        # Filtro por disponibilidad de stock
        in_stock = self.request.query_params.get('in_stock', None)
        if in_stock and in_stock.lower() in ['true', '1', 'yes']:
            # Solo productos con al menos una variante con stock disponible
            from django.db.models import Sum, F
            queryset = queryset.annotate(
                total_available=Sum(F('variants__stock') - F('variants__reserved_stock'))
            ).filter(total_available__gt=0)

        return queryset

    @action(detail=True, methods=['get'])
    def variants(self, request, pk=None):
        """
        Lista las variantes del producto solicitado.
        GET /api/v1/products/{id}/variants/
        """
        product = self.get_object()
        serializer = ProductVariantSerializer(
            product.variants.all(),
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """
        Lista las reseñas aprobadas de un producto.
        GET /api/v1/products/{id}/reviews/
        """
        product = self.get_object()
        reviews = product.reviews.filter(is_approved=True).select_related('user')
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)

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
            try:
                payment, payment_payload = PaymentService.create_order_payment(request.user, order)
            except ValueError as e:
                logger.error("Error al iniciar pago de orden %s: %s", order.id, e)
                from .services import OrderService
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

class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet de solo lectura para que un usuario pueda ver su historial de órdenes.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer
    STAFF_VISIBLE_STATUSES = {
        Order.OrderStatus.PENDING_PAYMENT,
        Order.OrderStatus.PAID,
        Order.OrderStatus.PREPARING,
        Order.OrderStatus.SHIPPED,
        Order.OrderStatus.RETURN_REQUESTED,
        Order.OrderStatus.RETURN_APPROVED,
        Order.OrderStatus.RETURN_REJECTED,
        Order.OrderStatus.FRAUD_ALERT,
    }
    STAFF_LOOKBACK_DAYS = 30

    def get_queryset(self):
        """Asegura que cada usuario solo pueda ver sus propias órdenes."""
        queryset = Order.objects.prefetch_related('items__variant__product')
        user = self.request.user
        if getattr(user, 'role', None) == CustomUser.Role.ADMIN:
            return queryset
        if getattr(user, 'role', None) == CustomUser.Role.STAFF:
            recent_threshold = timezone.now() - timedelta(days=self.STAFF_LOOKBACK_DAYS)
            return queryset.filter(
                Q(status__in=self.STAFF_VISIBLE_STATUSES)
                | Q(created_at__gte=recent_threshold)
            )
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


class ProductReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar reseñas de productos.
    - Los usuarios autenticados pueden crear, ver, actualizar y eliminar sus propias reseñas.
    - Los administradores pueden moderar y responder a cualquier reseña.
    """
    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """
        Los usuarios regulares ven solo reseñas aprobadas.
        Los administradores pueden ver todas las reseñas.
        """
        user = self.request.user
        queryset = ProductReview.objects.select_related('user', 'product')

        # Filtrar por producto si se especifica
        product_id = self.request.query_params.get('product', None)
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        # Los admins ven todas, los demás solo las aprobadas
        if not (user.is_authenticated and getattr(user, 'role', None) in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]):
            queryset = queryset.filter(is_approved=True)

        return queryset

    def get_serializer_class(self):
        """Selecciona el serializador según la acción."""
        if self.action == 'create':
            return ProductReviewCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ProductReviewUpdateSerializer
        return ProductReviewSerializer

    def perform_create(self, serializer):
        """Asigna el usuario actual a la reseña."""
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        """Solo permite actualizar reseñas propias."""
        if serializer.instance.user != self.request.user:
            raise PermissionError("No puedes editar reseñas de otros usuarios.")
        serializer.save()

    def perform_destroy(self, instance):
        """Solo permite eliminar reseñas propias o ser admin."""
        user = self.request.user
        is_admin = getattr(user, 'role', None) in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]

        if instance.user != user and not is_admin:
            raise PermissionError("No puedes eliminar reseñas de otros usuarios.")
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[DomainIsAdminUser])
    def respond(self, request, pk=None):
        """
        Permite a los administradores responder a una reseña.
        POST /api/v1/reviews/{id}/respond/
        Body: { "admin_response": "Gracias por tu comentario...", "is_approved": true }
        """
        review = self.get_object()
        serializer = AdminReviewResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review.admin_response = serializer.validated_data['admin_response']
        if 'is_approved' in serializer.validated_data:
            review.is_approved = serializer.validated_data['is_approved']
        review.save()

        return Response(ProductReviewSerializer(review).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_reviews(self, request):
        """
        Lista todas las reseñas del usuario autenticado.
        GET /api/v1/reviews/my_reviews/
        """
        reviews = ProductReview.objects.filter(user=request.user).select_related('product')
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)


class AdminProductViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para productos."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = Product.objects.all().prefetch_related('variants', 'images')
    serializer_class = AdminProductSerializer


class AdminProductVariantViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para variantes de producto."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = ProductVariant.objects.select_related('product')
    serializer_class = AdminProductVariantSerializer


class AdminProductImageViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para imágenes de producto."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = ProductImage.objects.select_related('product')
    serializer_class = AdminProductImageSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']


class AdminInventoryMovementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Permite registrar movimientos de inventario y consultarlos."""
    permission_classes = [DomainIsStaffOrAdmin]
    queryset = InventoryMovement.objects.select_related(
        'variant__product',
        'reference_order',
        'created_by',
    )
    serializer_class = AdminInventoryMovementSerializer
    http_method_names = ['get', 'post']

    def perform_create(self, serializer):
        with transaction.atomic():
            movement = serializer.save(created_by=self.request.user)
            self._apply_inventory_effect(movement)
            return movement

    def _apply_inventory_effect(self, movement):
        variant = ProductVariant.objects.select_for_update().get(pk=movement.variant_id)
        delta_stock, delta_reserved = AdminInventoryMovementSerializer.compute_deltas(
            movement.movement_type,
            movement.quantity,
        )
        update_fields = []
        if delta_stock:
            variant.stock = variant.stock + delta_stock
            update_fields.append('stock')
        if delta_reserved:
            variant.reserved_stock = variant.reserved_stock + delta_reserved
            update_fields.append('reserved_stock')
        if update_fields:
            variant.save(update_fields=update_fields)


class AdminOrderViewSet(viewsets.ModelViewSet):
    """CRUD administrativo para órdenes."""
    permission_classes = [DomainIsAdminUser]
    serializer_class = AdminOrderSerializer
    queryset = Order.objects.select_related('user').prefetch_related('items__variant__product').order_by('-created_at')

    http_method_names = ['get', 'put', 'patch', 'delete']

    def perform_update(self, serializer):
        order = serializer.save()
        return order
