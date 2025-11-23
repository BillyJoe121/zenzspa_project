# 🔍 ANÁLISIS DETALLADO DE MEJORAS - MÓDULO MARKETPLACE
## Análisis Pre-Producción Completo

**Fecha de Análisis**: 2025-11-23  
**Analista**: Antigravity AI  
**Módulo**: `marketplace/`  
**Total de Mejoras Identificadas**: 35+

---

## 📋 RESUMEN EJECUTIVO

El módulo marketplace implementa un sistema completo de e-commerce con gestión de inventario, carritos de compra, órdenes, pagos y devoluciones. El análisis identificó **35+ mejoras críticas y recomendadas** organizadas en 6 categorías principales:

- 🔴 **11 Críticas** - Deben implementarse antes de producción
- 🟡 **15 Importantes** - Primera iteración post-producción
- 🟢 **9 Mejoras** - Implementar según necesidad

### Áreas de Mayor Riesgo
1. **Race Conditions en Inventario** - Múltiples puntos de fallo
2. **Validaciones de Seguridad Insuficientes** - Manipulación de precios
3. **Manejo de Errores Incompleto** - Fallos silenciosos
4. **Testing Inexistente** - Sin cobertura de pruebas
5. **Observabilidad Limitada** - Difícil diagnosticar problemas

---

## 🔴 CRÍTICAS (11) - Implementar Antes de Producción

### **1. Race Condition en Stock al Agregar al Carrito**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` líneas 102-117  
**Código de Error Potencial**: `MKT-RACE-CART`

**Problema**: Al agregar items al carrito, se valida stock pero sin lock, permitiendo overselling.

```python
# CÓDIGO ACTUAL - VULNERABLE
cart_item, created = CartItem.objects.get_or_create(
    cart=cart,
    variant=variant,
    defaults={'quantity': quantity}
)
if not created:
    cart_item.quantity += quantity
    if cart_item.quantity > variant.stock:  # ⚠️ Stock puede cambiar aquí
        return Response({"error": "..."}, status=400)
    cart_item.save()
```

**Escenario de Fallo**:
1. Usuario A y B agregan simultáneamente el último item
2. Ambos pasan la validación de stock
3. Se crean 2 cart_items para 1 item disponible

**Solución**:
```python
# En views.py CartViewSet.add_item
from django.db import transaction

@action(detail=False, methods=['post'], url_path='add-item')
@transaction.atomic
def add_item(self, request):
    cart = self.get_cart()
    serializer = CartItemCreateUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    variant = serializer.validated_data['variant']
    quantity = serializer.validated_data['quantity']
    
    # Lock variant para evitar race condition
    variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        variant=variant,
        defaults={'quantity': quantity}
    )
    
    if not created:
        new_quantity = cart_item.quantity + quantity
    else:
        new_quantity = quantity
    
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
    
    cart_serializer = CartSerializer(cart, context={'request': request, 'view': self})
    return Response(cart_serializer.data, status=status.HTTP_201_CREATED)
```

**Impacto**: Previene overselling y quejas de clientes.

---

### **2. Validación de Stock Considera Solo `stock`, No `reserved_stock`**
**Severidad**: CRÍTICA  
**Ubicación**: `views.py` línea 112, `serializers.py` línea 189  
**Código de Error**: `MKT-STOCK-RESERVED`

**Problema**: Las validaciones de stock en el carrito solo verifican `variant.stock`, ignorando `reserved_stock`. Esto permite agregar al carrito items ya reservados por otras órdenes pendientes.

**Solución**:
```python
# En serializers.py CartItemCreateUpdateSerializer.validate
if quantity and quantity > (variant.stock - variant.reserved_stock):
    raise serializers.ValidationError(
        f"Stock insuficiente para '{variant}'. "
        f"Disponible: {variant.stock - variant.reserved_stock}."
    )
```

---

### **3. Falta Validación de Precio VIP en Checkout**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` líneas 69-72  
**Código de Error**: `MKT-PRICE-MANIPULATION`

**Problema**: Un usuario podría manipular su estado VIP después de agregar items al carrito pero antes del checkout, obteniendo precios incorrectos.

**Solución**:
```python
# En OrderCreationService.create_order, después de línea 72
# Validar que el usuario sigue siendo VIP si se aplicó precio VIP
if price_at_purchase == variant.vip_price:
    if not self.user.is_vip:
        raise BusinessLogicError(
            detail="El precio VIP ya no está disponible para este usuario.",
            internal_code="MKT-VIP-EXPIRED"
        )
```

---

### **4. Race Condition en `_capture_stock` Durante Confirmación de Pago**
**Severidad**: CRÍTICA  
**Ubicación**: `services.py` líneas 284-313  
**Código de Error**: `MKT-RACE-CAPTURE`

**Problema**: Entre la validación de stock (línea 288) y la captura (línea 304), otra transacción podría reducir el stock.

**Código Actual**:
```python
# VULNERABLE
for item in order.items.select_related('variant').select_for_update():
    variant = item.variant
    if variant.stock < item.quantity:  # ⚠️ Validación
        raise BusinessLogicError(...)
    # ... más código ...
    variant.stock -= item.quantity  # ⚠️ Stock pudo cambiar
    variant.save()
```

**Solución**: El `select_for_update()` ya está presente, pero debe aplicarse a la variante directamente:

```python
@classmethod
def _capture_stock(cls, order):
    for item in order.items.select_related('variant'):
        # Re-obtener variant con lock
        variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
        
        if variant.stock < item.quantity:
            raise BusinessLogicError(
                detail=f"Stock insuficiente para confirmar el pago del ítem {variant}.",
                internal_code="MKT-STOCK",
            )
        
        # Capturar stock de reserved_stock primero
        if variant.reserved_stock >= item.quantity:
            variant.reserved_stock -= item.quantity
        else:
            # Caso edge: reserva expiró parcialmente
            shortfall = item.quantity - variant.reserved_stock
            available = variant.stock - variant.reserved_stock
            if available < shortfall:
                raise BusinessLogicError(
                    detail=f"La reserva expiró y no hay stock suficiente para {variant}.",
                    internal_code="MKT-STOCK-EXPIRED",
                )
            variant.reserved_stock = 0
        
        variant.stock -= item.quantity
        variant.save(update_fields=['stock', 'reserved_stock', 'updated_at'])
        
        InventoryMovement.objects.create(
            variant=variant,
            quantity=item.quantity,
            movement_type=InventoryMovement.MovementType.SALE,
            reference_order=order,
            description="Venta confirmada",
            created_by=None,
        )
```

---

### **5. Falta Validación de Productos Inactivos en Checkout**
**Severidad**: ALTA  
**Ubicación**: `services.py` línea 59  
**Código de Error**: `MKT-INACTIVE-PRODUCT`

**Problema**: Se valida `variant.product.is_active` en `create_order`, pero un producto podría desactivarse entre agregar al carrito y hacer checkout.

**Solución Adicional**: Agregar validación en el serializer del carrito:
```python
# En serializers.py CartItemSerializer.get_subtotal
def get_subtotal(self, obj):
    if not obj.variant.product.is_active:
        # Marcar visualmente en el carrito
        return None
    # ... resto del código
```

Y en el checkout, agregar mensaje más claro:
```python
# En services.py línea 59
if not variant.product.is_active:
    raise BusinessLogicError(
        detail=f"El producto '{variant.product.name}' ya no está disponible. "
               f"Por favor, elimínalo de tu carrito.",
        internal_code="MKT-PRODUCT-INACTIVE"
    )
```

---

### **6. Falta Manejo de Timeout en Integración con Wompi**
**Severidad**: ALTA  
**Ubicación**: `views.py` líneas 203-209  
**Código de Error**: `MKT-PAYMENT-TIMEOUT`

**Problema**: Las llamadas a `PaymentService` no tienen timeout ni manejo de errores de red.

**Solución**:
```python
# En views.py CartViewSet.checkout, línea 203
try:
    amount_in_cents = int(order.total_amount * 100)
    base_url = getattr(settings, "WOMPI_BASE_URL", PaymentService.WOMPI_DEFAULT_BASE_URL)
    
    # Agregar timeout y manejo de errores
    try:
        acceptance_token = PaymentService._resolve_acceptance_token(base_url)
    except requests.Timeout:
        logger.error("Timeout al obtener acceptance token de Wompi")
        raise BusinessLogicError(
            detail="El servicio de pagos no está disponible. Intenta más tarde.",
            internal_code="MKT-PAYMENT-UNAVAILABLE"
        )
    except requests.RequestException as e:
        logger.exception("Error al comunicarse con Wompi: %s", e)
        raise BusinessLogicError(
            detail="Error al procesar el pago. Intenta más tarde.",
            internal_code="MKT-PAYMENT-ERROR"
        )
    
    signature = PaymentService._build_integrity_signature(
        reference=reference,
        amount_in_cents=amount_in_cents,
        currency=getattr(settings, "WOMPI_CURRENCY", "COP"),
    )
except Exception as e:
    # Si falla la preparación del pago, cancelar la orden
    logger.exception("Error preparando pago para orden %s: %s", order.id, e)
    OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
    raise BusinessLogicError(
        detail="No se pudo procesar tu orden. Intenta nuevamente.",
        internal_code="MKT-CHECKOUT-FAILED"
    )
```

---

### **7. Falta Validación de Monto Total en `confirm_payment`**
**Severidad**: ALTA  
**Ubicación**: `services.py` líneas 256-267  
**Código de Error**: `MKT-AMOUNT-MISMATCH`

**Problema**: `confirm_payment` valida precios unitarios pero no valida que el `total_amount` de la orden coincida con el monto pagado en Wompi.

**Solución**:
```python
# En services.py OrderService.confirm_payment
@classmethod
@transaction.atomic
def confirm_payment(cls, order, paid_amount=None):
    """
    Confirma el pago de una orden.
    
    Args:
        order: Orden a confirmar
        paid_amount: Monto pagado según gateway (opcional pero recomendado)
    """
    cls._validate_pricing(order)
    
    # Validar monto pagado si se proporciona
    if paid_amount is not None:
        if abs(paid_amount - order.total_amount) > Decimal('0.01'):
            raise BusinessLogicError(
                detail=f"El monto pagado ({paid_amount}) no coincide con el total de la orden ({order.total_amount}).",
                internal_code="MKT-AMOUNT-MISMATCH"
            )
    
    cls._capture_stock(order)
    order.reservation_expires_at = None
    order.save(update_fields=['reservation_expires_at', 'updated_at'])
    
    if order.status == Order.OrderStatus.CANCELLED:
        order.status = Order.OrderStatus.PAID
        order.save(update_fields=['status', 'updated_at'])
        return order
    
    return cls.transition_to(order, Order.OrderStatus.PAID)
```

Y actualizar la llamada en el webhook de Wompi para pasar el monto:
```python
# En el webhook de pagos (probablemente en spa/views.py)
OrderService.confirm_payment(order, paid_amount=transaction_amount)
```

---

### **8. Falta Idempotencia en `add_item` del Carrito**
**Severidad**: MEDIA-ALTA  
**Ubicación**: `views.py` líneas 87-121  
**Código de Error**: `MKT-DUPLICATE-ADD`

**Problema**: Si el usuario hace doble clic en "Agregar al carrito", se agregará 2 veces la cantidad.

**Solución**:
```python
# Agregar decorador idempotent_view
@action(detail=False, methods=['post'], url_path='add-item')
@idempotent_view(timeout=5)  # 5 segundos de ventana
@transaction.atomic
def add_item(self, request):
    # ... código existente
```

---

### **9. Falta Validación de Límite de Items en Carrito**
**Severidad**: MEDIA  
**Ubicación**: `views.py` línea 102  
**Código de Error**: `MKT-CART-LIMIT`

**Problema**: No hay límite en la cantidad de items diferentes o cantidad total en el carrito, permitiendo abuse.

**Solución**:
```python
# En views.py CartViewSet.add_item, después de línea 94
MAX_CART_ITEMS = 50
MAX_ITEM_QUANTITY = 100

if cart.items.count() >= MAX_CART_ITEMS:
    return Response(
        {
            "error": f"Has alcanzado el límite de {MAX_CART_ITEMS} productos diferentes en el carrito.",
            "code": "MKT-CART-LIMIT"
        },
        status=status.HTTP_400_BAD_REQUEST
    )

if quantity > MAX_ITEM_QUANTITY:
    return Response(
        {
            "error": f"La cantidad máxima por producto es {MAX_ITEM_QUANTITY}.",
            "code": "MKT-QUANTITY-LIMIT"
        },
        status=status.HTTP_400_BAD_REQUEST
    )
```

---

### **10. Falta Logging de Operaciones Críticas**
**Severidad**: MEDIA  
**Ubicación**: `services.py` - múltiples ubicaciones  
**Código de Error**: `MKT-AUDIT`

**Problema**: Operaciones críticas como creación de órdenes, confirmación de pagos, y devoluciones no se loguean adecuadamente.

**Solución**:
```python
# En OrderCreationService.create_order, después de línea 107
logger.info(
    "Orden creada: order_id=%s, user=%s, total=%s, items=%d",
    order.id, self.user.id, order.total_amount, len(items_to_create)
)

# En OrderService.confirm_payment, después de línea 267
logger.info(
    "Pago confirmado: order_id=%s, user=%s, total=%s",
    order.id, order.user.id, order.total_amount
)

# En OrderService.transition_to, después de línea 150
logger.info(
    "Transición de estado: order_id=%s, from=%s, to=%s, changed_by=%s",
    order.id, current, new_status, changed_by.id if changed_by else None
)
```

---

### **11. Testing Completamente Ausente**
**Severidad**: CRÍTICA  
**Ubicación**: `tests.py` - archivo vacío  
**Código de Error**: `MKT-NO-TESTS`

**Problema**: El archivo `tests.py` está vacío. No hay cobertura de pruebas para un módulo crítico de negocio.

**Solución**: Crear suite de tests completa:

```python
# marketplace/tests.py
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from users.models import CustomUser
from spa.models import ServiceCategory
from .models import (
    Product, ProductVariant, Cart, CartItem, 
    Order, OrderItem, InventoryMovement
)
from .services import OrderCreationService, OrderService, ReturnService

@pytest.mark.django_db
class TestProductVariant:
    """Tests para ProductVariant model"""
    
    def test_clean_vip_price_validation(self):
        """VIP price debe ser menor que regular price"""
        category = ServiceCategory.objects.create(name="Test")
        product = Product.objects.create(
            name="Test Product",
            description="Test",
            category=category
        )
        variant = ProductVariant(
            product=product,
            name="50ml",
            sku="TEST-001",
            price=Decimal('100.00'),
            vip_price=Decimal('150.00')  # ⚠️ Mayor que price
        )
        
        with pytest.raises(ValidationError):
            variant.clean()

@pytest.mark.django_db
class TestCartOperations:
    """Tests para operaciones del carrito"""
    
    def test_add_item_stock_validation(self, user, product_variant):
        """No se puede agregar más items que el stock disponible"""
        product_variant.stock = 5
        product_variant.save()
        
        cart = Cart.objects.create(user=user, is_active=True)
        
        # Agregar 5 items (OK)
        CartItem.objects.create(cart=cart, variant=product_variant, quantity=5)
        
        # Intentar agregar 1 más (debe fallar)
        # ... test de validación

    def test_concurrent_add_to_cart_race_condition(self, user, product_variant):
        """Test de race condition al agregar al carrito simultáneamente"""
        # Simular 2 requests concurrentes
        # ... test de concurrencia

@pytest.mark.django_db
class TestOrderCreation:
    """Tests para creación de órdenes"""
    
    def test_create_order_reserves_stock(self, user, cart_with_items):
        """Crear orden debe reservar stock"""
        variant = cart_with_items.items.first().variant
        initial_stock = variant.stock
        initial_reserved = variant.reserved_stock
        quantity = cart_with_items.items.first().quantity
        
        service = OrderCreationService(
            user=user,
            cart=cart_with_items,
            data={'delivery_option': Order.DeliveryOptions.PICKUP}
        )
        order = service.create_order()
        
        variant.refresh_from_db()
        assert variant.stock == initial_stock
        assert variant.reserved_stock == initial_reserved + quantity
    
    def test_create_order_empty_cart_fails(self, user):
        """No se puede crear orden con carrito vacío"""
        cart = Cart.objects.create(user=user, is_active=True)
        service = OrderCreationService(
            user=user,
            cart=cart,
            data={'delivery_option': Order.DeliveryOptions.PICKUP}
        )
        
        with pytest.raises(BusinessLogicError):
            service.create_order()

@pytest.mark.django_db
class TestOrderPaymentConfirmation:
    """Tests para confirmación de pago"""
    
    def test_confirm_payment_captures_stock(self, order_with_reservation):
        """Confirmar pago debe capturar stock de reserved_stock"""
        item = order_with_reservation.items.first()
        variant = item.variant
        initial_stock = variant.stock
        initial_reserved = variant.reserved_stock
        
        OrderService.confirm_payment(order_with_reservation)
        
        variant.refresh_from_db()
        assert variant.stock == initial_stock - item.quantity
        assert variant.reserved_stock == initial_reserved - item.quantity
    
    def test_confirm_payment_validates_pricing(self, order_with_reservation):
        """Confirmar pago debe validar que precios no cambiaron"""
        # Cambiar precio de variante
        item = order_with_reservation.items.first()
        item.variant.price = Decimal('999.99')
        item.variant.save()
        
        with pytest.raises(BusinessLogicError, match="MKT-PRICE"):
            OrderService.confirm_payment(order_with_reservation)

# ... más tests para returns, state transitions, etc.
```

**Prioridad**: Implementar al menos tests de integración básicos antes de producción.

---

## 🟡 IMPORTANTES (15) - Primera Iteración Post-Producción

### **12. Falta Validación de Cantidad Mínima/Máxima por Producto**
**Severidad**: MEDIA  
**Ubicación**: `models.py` ProductVariant  

**Problema**: No hay campos para definir cantidad mínima/máxima de compra por producto.

**Solución**:
```python
# En models.py ProductVariant
min_order_quantity = models.PositiveSmallIntegerField(
    default=1,
    verbose_name="Cantidad Mínima de Pedido"
)
max_order_quantity = models.PositiveSmallIntegerField(
    null=True,
    blank=True,
    verbose_name="Cantidad Máxima de Pedido"
)
```

---

### **13. Falta Sistema de Alertas de Stock Bajo**
**Severidad**: MEDIA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# En models.py ProductVariant
low_stock_threshold = models.PositiveIntegerField(
    default=10,
    verbose_name="Umbral de Stock Bajo"
)

# Nueva tarea en tasks.py
@shared_task
def check_low_stock_alerts():
    """Envía alertas cuando productos tienen stock bajo"""
    from .models import ProductVariant
    from notifications.services import NotificationService
    
    low_stock_variants = ProductVariant.objects.filter(
        product__is_active=True,
        stock__lte=models.F('low_stock_threshold'),
        stock__gt=0
    ).select_related('product')
    
    if low_stock_variants.exists():
        # Notificar a admins
        admin_users = CustomUser.objects.filter(role='ADMIN')
        for admin in admin_users:
            NotificationService.send_notification(
                user=admin,
                event_code="LOW_STOCK_ALERT",
                context={
                    "variants": [
                        f"{v.product.name} - {v.name}: {v.stock} unidades"
                        for v in low_stock_variants[:10]
                    ]
                }
            )
```

---

### **14. Falta Manejo de Vouchers/Cupones en Checkout**
**Severidad**: MEDIA  
**Ubicación**: `views.py` checkout, `models.py` Order  

**Problema**: El modelo Order tiene campo `voucher` pero no se usa en el checkout.

**Solución**:
```python
# En serializers.py CheckoutSerializer
voucher_code = serializers.CharField(required=False, allow_blank=True)

def validate_voucher_code(self, value):
    if value:
        try:
            voucher = Voucher.objects.get(code=value, is_active=True)
            if voucher.expiration_date and voucher.expiration_date < timezone.now().date():
                raise serializers.ValidationError("El voucher ha expirado.")
            if voucher.usage_count >= voucher.max_uses:
                raise serializers.ValidationError("El voucher ha alcanzado su límite de usos.")
            return voucher
        except Voucher.DoesNotExist:
            raise serializers.ValidationError("Código de voucher inválido.")
    return None

# En services.py OrderCreationService.create_order
# Aplicar descuento de voucher antes de línea 99
if 'voucher' in self.data and self.data['voucher']:
    voucher = self.data['voucher']
    if voucher.discount_type == Voucher.DiscountType.PERCENTAGE:
        discount = total_amount * (voucher.discount_value / 100)
    else:
        discount = voucher.discount_value
    total_amount = max(Decimal('0'), total_amount - discount)
    order.voucher = voucher
```

---

### **15. Falta Validación de Dirección de Envío**
**Severidad**: MEDIA  
**Ubicación**: `serializers.py` CheckoutSerializer línea 231  

**Problema**: Solo se valida que la dirección no esté vacía, pero no su formato o completitud.

**Solución**:
```python
# En serializers.py CheckoutSerializer
def validate_delivery_address(self, value):
    if not value or len(value.strip()) < 10:
        raise serializers.ValidationError(
            "La dirección debe tener al menos 10 caracteres."
        )
    
    # Validar que contenga información básica
    required_keywords = ['calle', 'carrera', 'avenida', 'transversal', 'diagonal']
    if not any(keyword in value.lower() for keyword in required_keywords):
        raise serializers.ValidationError(
            "La dirección debe incluir el tipo de vía (Calle, Carrera, etc.)."
        )
    
    return value.strip()
```

---

### **16. Falta Estimación de Fecha de Entrega**
**Severidad**: MEDIA  
**Ubicación**: `models.py` Order, `services.py` OrderCreationService  

**Problema**: No se calcula ni muestra fecha estimada de entrega al cliente.

**Solución**:
```python
# En models.py Order
estimated_delivery_date = models.DateField(
    null=True,
    blank=True,
    verbose_name="Fecha Estimada de Entrega"
)

# En services.py OrderCreationService.create_order, después de línea 45
# Calcular fecha estimada basada en preparation_days
max_prep_days = max(
    (item.variant.product.preparation_days for item in items_to_create),
    default=1
)
if self.data.get('delivery_option') == Order.DeliveryOptions.DELIVERY:
    # Agregar días de envío
    max_prep_days += 3
    
order.estimated_delivery_date = (
    timezone.now().date() + timedelta(days=max_prep_days)
)
```

---

### **17. Falta Notificación al Cliente de Cambios de Estado**
**Severidad**: MEDIA  
**Ubicación**: `services.py` OrderService  

**Problema**: Solo se envían emails, no notificaciones in-app.

**Solución**:
```python
# En services.py OrderService._dispatch_notifications
from notifications.services import NotificationService

@classmethod
def _dispatch_notifications(cls, order, new_status):
    if new_status in cls.STATE_NOTIFICATION_EVENTS:
        try:
            notify_order_status_change.delay(str(order.id), new_status)
        except Exception:
            logger.exception("No se pudo notificar el cambio de estado de la orden %s", order.id)
    
    # Agregar notificación in-app
    try:
        NotificationService.send_notification(
            user=order.user,
            event_code=cls.STATE_NOTIFICATION_EVENTS.get(new_status, "ORDER_STATUS_CHANGED"),
            context={
                "order_id": str(order.id),
                "status": new_status,
                "tracking_number": order.tracking_number,
            }
        )
    except Exception:
        logger.exception("No se pudo enviar notificación in-app para orden %s", order.id)
    
    cls._send_status_email(order, new_status)
```

---

### **18. Falta Validación de Transiciones de Estado Inválidas**
**Severidad**: MEDIA  
**Ubicación**: `services.py` OrderService.transition_to línea 141  

**Problema**: Se lanza excepción genérica, pero no se loguea el intento de transición inválida.

**Solución**:
```python
# En services.py OrderService.transition_to
if new_status not in allowed:
    logger.warning(
        "Intento de transición inválida: order_id=%s, from=%s, to=%s, user=%s",
        order.id, current, new_status, changed_by.id if changed_by else None
    )
    raise BusinessLogicError(
        detail=f"No se puede cambiar el estado de {current} a {new_status}.",
        internal_code="MKT-STATE",
        extra={"current_status": current, "attempted_status": new_status}
    )
```

---

### **19. Falta Rate Limiting en Endpoints Públicos**
**Severidad**: MEDIA  
**Ubicación**: `views.py` ProductViewSet  

**Problema**: El catálogo de productos es público sin rate limiting, vulnerable a scraping.

**Solución**:
```python
# Crear throttle en marketplace/throttling.py
from rest_framework.throttling import AnonRateThrottle

class ProductCatalogThrottle(AnonRateThrottle):
    scope = 'product_catalog'
    rate = '100/hour'

# En views.py ProductViewSet
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ProductCatalogThrottle]
    # ... resto del código

# En settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'product_catalog': '100/hour',
    }
}
```

---

### **20. Falta Paginación en Listado de Productos**
**Severidad**: MEDIA  
**Ubicación**: `views.py` ProductViewSet  

**Problema**: Sin paginación, listar todos los productos puede ser lento.

**Solución**:
```python
# En views.py ProductViewSet
from rest_framework.pagination import PageNumberPagination

class ProductPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    pagination_class = ProductPagination
    # ... resto del código
```

---

### **21. Falta Filtrado y Búsqueda en Productos**
**Severidad**: MEDIA  
**Ubicación**: `views.py` ProductViewSet  

**Solución**:
```python
# En views.py ProductViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    # ... resto del código
```

---

### **22. Falta Soft Delete en Productos**
**Severidad**: BAJA-MEDIA  
**Ubicación**: `models.py` Product  

**Problema**: Eliminar productos puede romper referencias en órdenes históricas.

**Solución**:
```python
# En models.py Product
# Cambiar de BaseModel a SoftDeleteModel
from core.models import SoftDeleteModel

class Product(SoftDeleteModel, BaseModel):
    # ... campos existentes
    
    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted']),
        ]
```

---

### **23. Falta Caché en Listado de Productos**
**Severidad**: MEDIA  
**Ubicación**: `views.py` ProductViewSet  

**Solución**:
```python
# En views.py ProductViewSet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    # ... código existente
    
    @method_decorator(cache_page(60 * 5))  # 5 minutos
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @method_decorator(cache_page(60 * 10))  # 10 minutos
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
```

---

### **24. Falta Validación de SKU Único al Crear Variantes**
**Severidad**: MEDIA  
**Ubicación**: `models.py` ProductVariant línea 50  

**Problema**: El campo SKU es único, pero no hay validación custom con mensaje claro.

**Solución**:
```python
# En models.py ProductVariant.clean
def clean(self):
    super().clean()
    if self.vip_price and self.vip_price >= self.price:
        raise ValidationError("El precio VIP debe ser menor que el precio regular")
    
    # Validar SKU único
    if self.sku:
        qs = ProductVariant.objects.filter(sku=self.sku)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({
                'sku': f"Ya existe una variante con el SKU '{self.sku}'."
            })
```

---

### **25. Falta Índice en `reservation_expires_at`**
**Severidad**: MEDIA  
**Ubicación**: `models.py` Order  

**Problema**: La tarea `release_expired_order_reservations` filtra por `reservation_expires_at` sin índice.

**Solución**:
```python
# En models.py Order.Meta
indexes = [
    models.Index(fields=['status']),
    models.Index(fields=['user', 'created_at']),
    models.Index(fields=['reservation_expires_at']),  # NUEVO
]
```

---

### **26. Falta Manejo de Errores en Tarea de Liberación de Reservas**
**Severidad**: MEDIA  
**Ubicación**: `tasks.py` release_expired_order_reservations  

**Problema**: Si falla la transición de una orden, toda la tarea falla.

**Solución**:
```python
# En tasks.py release_expired_order_reservations
@shared_task
def release_expired_order_reservations():
    from .models import Order
    from .services import OrderService
    
    now = timezone.now()
    expired_orders = Order.objects.filter(
        status=Order.OrderStatus.PENDING_PAYMENT,
        reservation_expires_at__isnull=False,
        reservation_expires_at__lt=now,
    )
    
    count = 0
    errors = 0
    
    for order in expired_orders:
        try:
            with transaction.atomic():
                order_locked = Order.objects.select_for_update().get(pk=order.pk)
                # Verificar nuevamente el estado por si cambió
                if order_locked.status == Order.OrderStatus.PENDING_PAYMENT:
                    OrderService.transition_to(order_locked, Order.OrderStatus.CANCELLED)
                    count += 1
        except Exception as e:
            errors += 1
            logger.exception("Error liberando reserva de orden %s: %s", order.id, e)
    
    result = f"Reservas liberadas: {count}"
    if errors > 0:
        result += f", errores: {errors}"
    
    return result
```

---

## 🟢 MEJORAS (9) - Implementar Según Necesidad

### **27. Agregar Campo de Peso/Dimensiones para Cálculo de Envío**
**Severidad**: BAJA  
**Ubicación**: `models.py` ProductVariant  

**Solución**:
```python
# En models.py ProductVariant
weight_grams = models.PositiveIntegerField(
    null=True,
    blank=True,
    verbose_name="Peso en Gramos"
)
dimensions_cm = models.CharField(
    max_length=50,
    blank=True,
    verbose_name="Dimensiones (LxWxH en cm)",
    help_text="Formato: 10x5x3"
)
```

---

### **28. Implementar Sistema de Reviews/Calificaciones**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class ProductReview(BaseModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_reviews'
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Orden asociada para verificar compra"
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(i, i) for i in range(1, 6)],
        verbose_name="Calificación (1-5)"
    )
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('product', 'user', 'order')
        ordering = ['-created_at']
```

---

### **29. Agregar Historial de Precios**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class PriceHistory(BaseModel):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='price_history'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    
    class Meta:
        ordering = ['-created_at']

# Signal para guardar historial
from django.db.models.signals import pre_save
from django.dispatch import receiver

@receiver(pre_save, sender=ProductVariant)
def save_price_history(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = ProductVariant.objects.get(pk=instance.pk)
            if old.price != instance.price or old.vip_price != instance.vip_price:
                PriceHistory.objects.create(
                    variant=instance,
                    price=old.price,
                    vip_price=old.vip_price
                )
        except ProductVariant.DoesNotExist:
            pass
```

---

### **30. Implementar Wishlist/Lista de Deseos**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class Wishlist(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist'
    )

class WishlistItem(BaseModel):
    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    
    class Meta:
        unique_together = ('wishlist', 'product')
```

---

### **31. Agregar Notificaciones de Restock**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class RestockNotification(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='restock_notifications'
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='restock_notifications'
    )
    notified = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'variant')

# Signal para notificar cuando hay restock
@receiver(post_save, sender=InventoryMovement)
def notify_restock(sender, instance, created, **kwargs):
    if created and instance.movement_type == InventoryMovement.MovementType.RESTOCK:
        notifications = RestockNotification.objects.filter(
            variant=instance.variant,
            notified=False
        ).select_related('user')
        
        for notification in notifications:
            NotificationService.send_notification(
                user=notification.user,
                event_code="PRODUCT_RESTOCKED",
                context={
                    "product_name": instance.variant.product.name,
                    "variant_name": instance.variant.name,
                }
            )
            notification.notified = True
            notification.save()
```

---

### **32. Implementar Descuentos por Cantidad**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class BulkDiscount(BaseModel):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='bulk_discounts'
    )
    min_quantity = models.PositiveIntegerField()
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Porcentaje de descuento (0-100)"
    )
    
    class Meta:
        unique_together = ('variant', 'min_quantity')
        ordering = ['variant', 'min_quantity']
```

---

### **33. Agregar Productos Relacionados/Recomendados**
**Severidad**: BAJA  
**Ubicación**: `models.py` Product  

**Solución**:
```python
# En models.py Product
related_products = models.ManyToManyField(
    'self',
    blank=True,
    symmetrical=False,
    related_name='recommended_by',
    verbose_name="Productos Relacionados"
)
```

---

### **34. Implementar Sistema de Tags/Etiquetas**
**Severidad**: BAJA  
**Ubicación**: Nueva funcionalidad  

**Solución**:
```python
# Nuevo modelo en models.py
class ProductTag(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    
    class Meta:
        ordering = ['name']

# En models.py Product
tags = models.ManyToManyField(
    ProductTag,
    blank=True,
    related_name='products',
    verbose_name="Etiquetas"
)
```

---

### **35. Agregar Métricas de Conversión en Admin**
**Severidad**: BAJA  
**Ubicación**: `admin.py`  

**Solución**:
```python
# En admin.py OrderAdmin
from django.db.models import Count, Sum, Avg
from django.utils.html import format_html

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'delivery_option', 'created_at')
    list_filter = ('status', 'delivery_option', 'created_at')
    search_fields = ('user__email', 'tracking_number')
    raw_id_fields = ('user', 'associated_appointment', 'voucher')
    inlines = [OrderItemInline]
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Métricas de hoy
        today = timezone.now().date()
        today_orders = Order.objects.filter(created_at__date=today)
        
        stats = today_orders.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total_amount'),
            avg_order_value=Avg('total_amount'),
            paid_orders=Count('id', filter=models.Q(status=Order.OrderStatus.PAID)),
        )
        
        extra_context['today_stats'] = {
            'total_orders': stats['total_orders'] or 0,
            'total_revenue': stats['total_revenue'] or Decimal('0'),
            'avg_order_value': stats['avg_order_value'] or Decimal('0'),
            'conversion_rate': (
                (stats['paid_orders'] / stats['total_orders'] * 100)
                if stats['total_orders'] > 0 else 0
            ),
        }
        
        return super().changelist_view(request, extra_context)
```

---

## 📊 RESUMEN DE PRIORIDADES

### 🔴 CRÍTICAS (11) - Implementar ANTES de Producción
1. **#1** - Race condition en stock al agregar al carrito
2. **#2** - Validación de stock considera solo `stock`, no `reserved_stock`
3. **#3** - Falta validación de precio VIP en checkout
4. **#4** - Race condition en `_capture_stock`
5. **#5** - Falta validación de productos inactivos en checkout
6. **#6** - Falta manejo de timeout en integración Wompi
7. **#7** - Falta validación de monto total en `confirm_payment`
8. **#8** - Falta idempotencia en `add_item`
9. **#9** - Falta validación de límite de items en carrito
10. **#10** - Falta logging de operaciones críticas
11. **#11** - Testing completamente ausente

### 🟡 IMPORTANTES (15) - Primera Iteración Post-Producción
12. **#12** - Falta validación de cantidad mínima/máxima por producto
13. **#13** - Falta sistema de alertas de stock bajo
14. **#14** - Falta manejo de vouchers/cupones en checkout
15. **#15** - Falta validación de dirección de envío
16. **#16** - Falta estimación de fecha de entrega
17. **#17** - Falta notificación in-app de cambios de estado
18. **#18** - Falta logging de transiciones inválidas
19. **#19** - Falta rate limiting en endpoints públicos
20. **#20** - Falta paginación en listado de productos
21. **#21** - Falta filtrado y búsqueda en productos
22. **#22** - Falta soft delete en productos
23. **#23** - Falta caché en listado de productos
24. **#24** - Falta validación de SKU único
25. **#25** - Falta índice en `reservation_expires_at`
26. **#26** - Falta manejo de errores en tarea de liberación

### 🟢 MEJORAS (9) - Implementar Según Necesidad
27. **#27** - Agregar peso/dimensiones para envío
28. **#28** - Sistema de reviews/calificaciones
29. **#29** - Historial de precios
30. **#30** - Wishlist/lista de deseos
31. **#31** - Notificaciones de restock
32. **#32** - Descuentos por cantidad
33. **#33** - Productos relacionados
34. **#34** - Sistema de tags/etiquetas
35. **#35** - Métricas de conversión en admin

---

## 💡 RECOMENDACIONES ADICIONALES

### Monitoreo en Producción
- Configurar alertas para:
  - Tasa de órdenes canceladas > 10%
  - Tiempo de checkout > 30s
  - Errores de stock > 5/hora
  - Fallos de integración Wompi > 2%

### Documentación
- Crear runbook para incidentes de inventario
- Documentar flujo completo de checkout
- Crear guía de troubleshooting para devoluciones

### Escalabilidad
- Considerar Redis para locks distribuidos
- Implementar circuit breaker para Wompi
- Evaluar CDN para imágenes de productos

### Seguridad
- Implementar CSRF tokens en checkout
- Validar integridad de datos en webhooks
- Agregar 2FA para operaciones de admin críticas

---

**Próximos Pasos Recomendados**:
1. Implementar las 11 mejoras críticas
2. Crear suite de tests básica (al menos 50% cobertura)
3. Configurar monitoreo y alertas
4. Realizar pruebas de carga
5. Documentar procesos operativos
