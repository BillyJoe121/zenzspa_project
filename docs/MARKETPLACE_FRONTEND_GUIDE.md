# 🛒 Guía Completa: Carrito y Checkout de Productos - Frontend

**Fecha**: 13 de Diciembre, 2024  
**Versión**: 1.0  
**Backend**: Django REST Framework  
**Frontend**: React + TypeScript + TanStack Query

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Endpoints del Backend](#endpoints-del-backend)
4. [Tipos TypeScript](#tipos-typescript)
5. [Hooks de React Query](#hooks-de-react-query)
6. [Componentes a Crear](#componentes-a-crear)
7. [Páginas a Crear](#páginas-a-crear)
8. [Flujos de Usuario](#flujos-de-usuario)
9. [Integración con Wompi](#integración-con-wompi)
10. [Manejo de Errores](#manejo-de-errores)

---

## 🎯 Resumen Ejecutivo

### ¿Qué vamos a construir?

Un sistema completo de carrito de compras y checkout para productos que incluye:

- ✅ **Catálogo de productos** con filtros y búsqueda
- ✅ **Carrito de compras** persistente (7 días)
- ✅ **Checkout** con múltiples opciones de entrega
- ✅ **Integración con Wompi** para pagos
- ✅ **Precios VIP** automáticos
- ✅ **Gestión de stock** en tiempo real
- ✅ **Historial de órdenes**

### Características Clave

- **Precios VIP automáticos**: El backend calcula automáticamente el precio según el rol del usuario
- **Stock en tiempo real**: Validación de disponibilidad antes de agregar al carrito
- **Carrito persistente**: Se mantiene por 7 días
- **Checkout con opciones**: Recogida en local, envío a domicilio, o asociar a cita
- **Pago con Wompi**: Integración completa con el gateway de pagos

---

## 🏗️ Arquitectura del Sistema

### Flujo General

```
┌─────────────┐
│   Usuario   │
└──────┬──────┘
       │
       │ 1. Navega catálogo
       ▼
┌─────────────────────┐
│ ProductListPage     │
│ - Filtros           │
│ - Búsqueda          │
│ - Grid de productos │
└──────┬──────────────┘
       │
       │ 2. Click en producto
       ▼
┌─────────────────────┐
│ ProductDetailPage   │
│ - Selector variante │
│ - Precio VIP        │
│ - [Agregar]         │
└──────┬──────────────┘
       │
       │ 3. Agregar al carrito
       ▼
┌─────────────────────┐
│ CartPage            │
│ - Lista items       │
│ - Subtotales        │
│ - Total             │
│ - [Checkout]        │
└──────┬──────────────┘
       │
       │ 4. Proceder a pago
       ▼
┌─────────────────────┐
│ CheckoutPage        │
│ - Opción entrega    │
│ - Dirección         │
│ - Resumen           │
│ - [Pagar]           │
└──────┬──────────────┘
       │
       │ 5. Pago con Wompi
       ▼
┌─────────────────────┐
│ Wompi Gateway       │
└──────┬──────────────┘
       │
       │ 6. Resultado
       ▼
┌─────────────────────┐
│ OrderResultPage     │
│ - Estado orden      │
│ - Detalles          │
└─────────────────────┘
```

---

## 🔌 Endpoints del Backend

### 1. Productos

#### Listar Productos
```
GET /api/v1/marketplace/products/
```

**Query Parameters**:
- `search`: Buscar en nombre y descripción
- `category`: Filtrar por categoría (UUID)
- `min_price`: Precio mínimo
- `max_price`: Precio máximo
- `in_stock`: Solo productos con stock (`true`/`false`)

**Respuesta**:
```json
{
  "count": 25,
  "next": "http://api/marketplace/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid-product-1",
      "name": "Crema Hidratante Premium",
      "price": "85000.00",
      "vip_price": "72250.00",
      "stock": 45,
      "main_image": {
        "image": "/media/product_images/crema.jpg",
        "is_primary": true,
        "alt_text": "Crema Hidratante"
      }
    }
  ]
}
```

#### Detalle de Producto
```
GET /api/v1/marketplace/products/{id}/
```

**Respuesta**:
```json
{
  "id": "uuid-product-1",
  "name": "Crema Hidratante Premium",
  "description": "Crema facial con ácido hialurónico...",
  "price": "85000.00",
  "vip_price": "72250.00",
  "stock": 45,
  "category": "uuid-cat",
  "preparation_days": 2,
  "images": [
    {
      "image": "/media/product_images/crema.jpg",
      "is_primary": true,
      "alt_text": "Crema Hidratante"
    }
  ],
  "variants": [
    {
      "id": "uuid-var-1",
      "sku": "CREMA-50ML",
      "name": "50ml",
      "price": "85000.00",
      "vip_price": "72250.00",
      "stock": 25
    },
    {
      "id": "uuid-var-2",
      "sku": "CREMA-100ML",
      "name": "100ml",
      "price": "150000.00",
      "vip_price": "127500.00",
      "stock": 20
    }
  ],
  "average_rating": 4.5,
  "review_count": 12
}
```

---

### 2. Carrito

#### Obtener Mi Carrito
```
GET /api/v1/marketplace/cart/my-cart/
```

**Requiere**: `IsAuthenticated`

**Respuesta**:
```json
{
  "id": "uuid-cart",
  "user": "uuid-user",
  "is_active": true,
  "items": [
    {
      "id": "uuid-item-1",
      "product": {
        "id": "uuid-product",
        "name": "Crema Hidratante Premium"
      },
      "variant": {
        "id": "uuid-var",
        "sku": "CREMA-50ML",
        "name": "50ml",
        "price": "85000.00",
        "vip_price": "72250.00",
        "stock": 25
      },
      "quantity": 2,
      "subtotal": "144500.00"
    }
  ],
  "total": "144500.00"
}
```

#### Agregar Item al Carrito
```
POST /api/v1/marketplace/cart/add-item/
```

**Body**:
```json
{
  "variant_id": "uuid-variant",
  "quantity": 1
}
```

O usando SKU:
```json
{
  "sku": "CREMA-50ML",
  "quantity": 1
}
```

**Respuesta**: Carrito completo actualizado

**Errores posibles**:
- `MKT-CART-LIMIT`: Límite de 50 productos diferentes
- `MKT-QUANTITY-LIMIT`: Máximo 100 unidades por producto
- `MKT-STOCK-CART`: Stock insuficiente

#### Actualizar Cantidad de Item
```
PUT /api/v1/marketplace/cart/{cart_item_id}/update-item/
```

**Body**:
```json
{
  "quantity": 3
}
```

#### Eliminar Item del Carrito
```
DELETE /api/v1/marketplace/cart/{cart_item_id}/remove-item/
```

---

### 3. Checkout

#### Crear Orden desde Carrito
```
POST /api/v1/marketplace/cart/checkout/
```

**Requiere**: 
- `IsAuthenticated`
- Consentimiento de compra firmado

**Body**:
```json
{
  "delivery_option": "DELIVERY",
  "delivery_address": "Calle 123 #45-67, Apartamento 801, Bogotá",
  "associated_appointment_id": "uuid-appointment" // Opcional
}
```

**Opciones de entrega**:
- `PICKUP`: Recogida en local
- `DELIVERY`: Envío a domicilio (requiere `delivery_address`)
- `ASSOCIATE_TO_APPOINTMENT`: Asociar a cita futura (requiere `associated_appointment_id`)

**Respuesta**:
```json
{
  "order": {
    "id": "uuid-order",
    "user_email": "user@example.com",
    "status": "PENDING_PAYMENT",
    "total_amount": "144500.00",
    "delivery_option": "DELIVERY",
    "delivery_address": "Calle 123 #45-67...",
    "created_at": "2024-12-13T22:00:00Z",
    "items": [
      {
        "id": "uuid-item",
        "product_name": "Crema Hidratante Premium",
        "variant_name": "50ml",
        "sku": "CREMA-50ML",
        "quantity": 2,
        "price_at_purchase": "72250.00"
      }
    ]
  },
  "payment": {
    "publicKey": "pub_test_xxxxx",
    "amountInCents": 14450000,
    "reference": "order_uuid-order_timestamp",
    "signatureIntegrity": "hash_signature",
    "redirectUrl": "http://localhost:3000/marketplace/payment-result",
    "currency": "COP"
  }
}
```

---

### 4. Órdenes

#### Listar Mis Órdenes
```
GET /api/v1/marketplace/orders/
```

**Requiere**: `IsAuthenticated`

**Respuesta**:
```json
{
  "count": 5,
  "results": [
    {
      "id": "uuid-order",
      "user_email": "user@example.com",
      "status": "DELIVERED",
      "total_amount": "144500.00",
      "delivery_option": "DELIVERY",
      "created_at": "2024-12-10T15:00:00Z",
      "items": [...]
    }
  ]
}
```

#### Detalle de Orden
```
GET /api/v1/marketplace/orders/{id}/
```

---

## 📝 Tipos TypeScript

### Archivo: `types/marketplace.ts`

```typescript
// ============================================================================
// PRODUCTOS
// ============================================================================

export interface ProductImage {
  image: string;
  is_primary: boolean;
  alt_text: string;
}

export interface ProductVariant {
  id: string;
  sku: string;
  name: string;
  price: string;
  vip_price: string | null;
  stock: number;
}

export interface Product {
  id: string;
  name: string;
  description?: string;
  price: string;
  vip_price: string | null;
  stock: number;
  main_image: ProductImage | null;
  category?: string;
  preparation_days?: number;
  images?: ProductImage[];
  variants?: ProductVariant[];
  average_rating?: number;
  review_count?: number;
}

export interface ProductListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Product[];
}

// ============================================================================
// CARRITO
// ============================================================================

export interface CartItemVariant {
  id: string;
  sku: string;
  name: string;
  price: string;
  vip_price: string | null;
  stock: number;
}

export interface CartItem {
  id: string;
  product: {
    id: string;
    name: string;
  };
  variant: CartItemVariant;
  quantity: number;
  subtotal: string;
}

export interface Cart {
  id: string;
  user: string;
  is_active: boolean;
  items: CartItem[];
  total: string;
}

export interface AddToCartRequest {
  variant_id?: string;
  sku?: string;
  quantity: number;
}

export interface UpdateCartItemRequest {
  quantity: number;
}

// ============================================================================
// CHECKOUT Y ÓRDENES
// ============================================================================

export type DeliveryOption = 'PICKUP' | 'DELIVERY' | 'ASSOCIATE_TO_APPOINTMENT';

export interface CheckoutRequest {
  delivery_option: DeliveryOption;
  delivery_address?: string;
  associated_appointment_id?: string;
}

export interface OrderItem {
  id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  quantity: number;
  price_at_purchase: string;
}

export type OrderStatus =
  | 'PENDING_PAYMENT'
  | 'PAID'
  | 'PREPARING'
  | 'SHIPPED'
  | 'DELIVERED'
  | 'CANCELLED'
  | 'RETURN_REQUESTED'
  | 'RETURN_APPROVED'
  | 'RETURN_REJECTED'
  | 'REFUNDED'
  | 'FRAUD_ALERT';

export interface Order {
  id: string;
  user_email: string;
  status: OrderStatus;
  total_amount: string;
  delivery_option: DeliveryOption;
  delivery_address?: string;
  associated_appointment?: string;
  tracking_number?: string;
  return_reason?: string;
  return_requested_at?: string;
  created_at: string;
  items: OrderItem[];
}

export interface WompiPaymentData {
  publicKey: string;
  amountInCents: number;
  reference: string;
  signatureIntegrity: string;
  redirectUrl: string;
  currency: string;
}

export interface CheckoutResponse {
  order: Order;
  payment: WompiPaymentData;
}

export interface OrderListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Order[];
}

// ============================================================================
// FILTROS Y BÚSQUEDA
// ============================================================================

export interface ProductFilters {
  search?: string;
  category?: string;
  min_price?: number;
  max_price?: number;
  in_stock?: boolean;
  page?: number;
}
```

---

## 🪝 Hooks de React Query

### Archivo: `hooks/useMarketplace.ts`

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import type {
  Product,
  ProductListResponse,
  ProductFilters,
  Cart,
  AddToCartRequest,
  UpdateCartItemRequest,
  CheckoutRequest,
  CheckoutResponse,
  Order,
  OrderListResponse,
} from '@/types/marketplace';

// ============================================================================
// PRODUCTOS
// ============================================================================

export const useProducts = (filters?: ProductFilters) => {
  return useQuery({
    queryKey: ['products', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      
      if (filters?.search) params.append('search', filters.search);
      if (filters?.category) params.append('category', filters.category);
      if (filters?.min_price) params.append('min_price', filters.min_price.toString());
      if (filters?.max_price) params.append('max_price', filters.max_price.toString());
      if (filters?.in_stock !== undefined) params.append('in_stock', filters.in_stock.toString());
      if (filters?.page) params.append('page', filters.page.toString());
      
      const response = await api.get<ProductListResponse>(
        `/api/v1/marketplace/products/?${params.toString()}`
      );
      return response.data;
    },
  });
};

export const useProduct = (productId: string) => {
  return useQuery({
    queryKey: ['product', productId],
    queryFn: async () => {
      const response = await api.get<Product>(
        `/api/v1/marketplace/products/${productId}/`
      );
      return response.data;
    },
    enabled: !!productId,
  });
};

// ============================================================================
// CARRITO
// ============================================================================

export const useCart = () => {
  return useQuery({
    queryKey: ['cart'],
    queryFn: async () => {
      const response = await api.get<Cart>('/api/v1/marketplace/cart/my-cart/');
      return response.data;
    },
    // Refetch cada 30 segundos para mantener stock actualizado
    refetchInterval: 30000,
  });
};

export const useAddToCart = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (data: AddToCartRequest) => {
      const response = await api.post<Cart>(
        '/api/v1/marketplace/cart/add-item/',
        data
      );
      return response.data;
    },
    onSuccess: (data) => {
      // Actualizar el carrito en el cache
      queryClient.setQueryData(['cart'], data);
      
      // Invalidar productos para actualizar stock
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });
};

export const useUpdateCartItem = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ itemId, data }: { itemId: string; data: UpdateCartItemRequest }) => {
      const response = await api.put<Cart>(
        `/api/v1/marketplace/cart/${itemId}/update-item/`,
        data
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['cart'], data);
    },
  });
};

export const useRemoveCartItem = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (itemId: string) => {
      await api.delete(`/api/v1/marketplace/cart/${itemId}/remove-item/`);
    },
    onSuccess: () => {
      // Refetch del carrito
      queryClient.invalidateQueries({ queryKey: ['cart'] });
    },
  });
};

// ============================================================================
// CHECKOUT
// ============================================================================

export const useCheckout = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async (data: CheckoutRequest) => {
      const response = await api.post<CheckoutResponse>(
        '/api/v1/marketplace/cart/checkout/',
        data
      );
      return response.data;
    },
    onSuccess: () => {
      // Limpiar el carrito del cache
      queryClient.invalidateQueries({ queryKey: ['cart'] });
      
      // Invalidar órdenes para mostrar la nueva
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
};

// ============================================================================
// ÓRDENES
// ============================================================================

export const useOrders = () => {
  return useQuery({
    queryKey: ['orders'],
    queryFn: async () => {
      const response = await api.get<OrderListResponse>('/api/v1/marketplace/orders/');
      return response.data;
    },
  });
};

export const useOrder = (orderId: string) => {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: async () => {
      const response = await api.get<Order>(`/api/v1/marketplace/orders/${orderId}/`);
      return response.data;
    },
    enabled: !!orderId,
  });
};
```

---

## 🧩 Componentes a Crear

### 1. ProductCard

**Ubicación**: `components/marketplace/ProductCard.tsx`

```typescript
import { Product } from '@/types/marketplace';
import { useAuth } from '@/hooks/useAuth';
import { Link } from 'react-router-dom';

interface ProductCardProps {
  product: Product;
}

export const ProductCard = ({ product }: ProductCardProps) => {
  const { user } = useAuth();
  const isVIP = user?.role === 'VIP';
  const hasVIPPrice = product.vip_price !== null;
  
  const price = parseFloat(product.price);
  const vipPrice = product.vip_price ? parseFloat(product.vip_price) : null;
  const savings = vipPrice ? price - vipPrice : 0;

  return (
    <Link to={`/marketplace/products/${product.id}`} className="product-card">
      {/* Imagen */}
      {product.main_image && (
        <div className="product-image">
          <img 
            src={product.main_image.image} 
            alt={product.main_image.alt_text}
          />
          {product.stock === 0 && (
            <div className="out-of-stock-badge">Agotado</div>
          )}
        </div>
      )}
      
      {/* Información */}
      <div className="product-info">
        <h3>{product.name}</h3>
        
        {/* Precios */}
        <div className="product-pricing">
          {isVIP && hasVIPPrice ? (
            <>
              <span className="original-price line-through">
                ${price.toLocaleString('es-CO')}
              </span>
              <span className="vip-price text-gold">
                ${vipPrice?.toLocaleString('es-CO')}
              </span>
              <span className="savings text-green-600 text-sm">
                Ahorras ${savings.toLocaleString('es-CO')}
              </span>
            </>
          ) : hasVIPPrice ? (
            <>
              <span className="price">
                ${price.toLocaleString('es-CO')}
              </span>
              <p className="vip-promo text-sm text-gold">
                💎 Precio VIP: ${vipPrice?.toLocaleString('es-CO')}
              </p>
            </>
          ) : (
            <span className="price">
              ${price.toLocaleString('es-CO')}
            </span>
          )}
        </div>
        
        {/* Rating */}
        {product.average_rating && (
          <div className="product-rating">
            ⭐ {product.average_rating.toFixed(1)} ({product.review_count} reseñas)
          </div>
        )}
      </div>
    </Link>
  );
};
```

---

### 2. CartItemCard

**Ubicación**: `components/marketplace/CartItemCard.tsx`

```typescript
import { CartItem } from '@/types/marketplace';
import { useUpdateCartItem, useRemoveCartItem } from '@/hooks/useMarketplace';
import { useState } from 'react';

interface CartItemCardProps {
  item: CartItem;
}

export const CartItemCard = ({ item }: CartItemCardProps) => {
  const [quantity, setQuantity] = useState(item.quantity);
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();

  const handleQuantityChange = (newQuantity: number) => {
    if (newQuantity < 1) return;
    if (newQuantity > item.variant.stock) {
      alert(`Solo hay ${item.variant.stock} unidades disponibles`);
      return;
    }
    
    setQuantity(newQuantity);
    updateItem.mutate({
      itemId: item.id,
      data: { quantity: newQuantity }
    });
  };

  const handleRemove = () => {
    if (confirm('¿Eliminar este producto del carrito?')) {
      removeItem.mutate(item.id);
    }
  };

  return (
    <div className="cart-item">
      <div className="item-info">
        <h4>{item.product.name}</h4>
        <p className="variant-name">{item.variant.name}</p>
        <p className="sku text-sm text-gray-500">SKU: {item.variant.sku}</p>
      </div>
      
      <div className="item-quantity">
        <button 
          onClick={() => handleQuantityChange(quantity - 1)}
          disabled={quantity <= 1}
        >
          -
        </button>
        <span>{quantity}</span>
        <button 
          onClick={() => handleQuantityChange(quantity + 1)}
          disabled={quantity >= item.variant.stock}
        >
          +
        </button>
      </div>
      
      <div className="item-price">
        <p className="subtotal">
          ${parseFloat(item.subtotal).toLocaleString('es-CO')}
        </p>
        <p className="unit-price text-sm text-gray-500">
          ${parseFloat(item.variant.vip_price || item.variant.price).toLocaleString('es-CO')} c/u
        </p>
      </div>
      
      <button onClick={handleRemove} className="remove-btn">
        🗑️
      </button>
    </div>
  );
};
```

---

### 3. VariantSelector

**Ubicación**: `components/marketplace/VariantSelector.tsx`

```typescript
import { ProductVariant } from '@/types/marketplace';
import { useAuth } from '@/hooks/useAuth';

interface VariantSelectorProps {
  variants: ProductVariant[];
  selectedVariant: ProductVariant | null;
  onSelectVariant: (variant: ProductVariant) => void;
}

export const VariantSelector = ({
  variants,
  selectedVariant,
  onSelectVariant,
}: VariantSelectorProps) => {
  const { user } = useAuth();
  const isVIP = user?.role === 'VIP';

  return (
    <div className="variant-selector">
      <label className="font-semibold">Presentación:</label>
      <div className="variants-grid">
        {variants.map((variant) => {
          const price = parseFloat(variant.price);
          const vipPrice = variant.vip_price ? parseFloat(variant.vip_price) : null;
          const displayPrice = isVIP && vipPrice ? vipPrice : price;
          const isSelected = selectedVariant?.id === variant.id;
          const isOutOfStock = variant.stock === 0;

          return (
            <button
              key={variant.id}
              onClick={() => !isOutOfStock && onSelectVariant(variant)}
              disabled={isOutOfStock}
              className={`variant-option ${isSelected ? 'selected' : ''} ${isOutOfStock ? 'disabled' : ''}`}
            >
              <span className="variant-name">{variant.name}</span>
              <span className="variant-price">
                ${displayPrice.toLocaleString('es-CO')}
              </span>
              {isOutOfStock && (
                <span className="out-of-stock">Agotado</span>
              )}
              {variant.stock > 0 && variant.stock < 5 && (
                <span className="low-stock">¡Solo {variant.stock}!</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
```

---

## 📄 Páginas a Crear

### 1. ProductListPage

**Ubicación**: `pages/marketplace/ProductListPage.tsx`

```typescript
import { useState } from 'react';
import { useProducts } from '@/hooks/useMarketplace';
import { ProductCard } from '@/components/marketplace/ProductCard';
import { ProductFilters } from '@/types/marketplace';

export const ProductListPage = () => {
  const [filters, setFilters] = useState<ProductFilters>({});
  const { data, isLoading } = useProducts(filters);

  if (isLoading) return <div>Cargando productos...</div>;

  return (
    <div className="product-list-page">
      <h1>Productos</h1>
      
      {/* Filtros */}
      <div className="filters">
        <input
          type="text"
          placeholder="Buscar productos..."
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        
        <label>
          <input
            type="checkbox"
            onChange={(e) => setFilters({ ...filters, in_stock: e.target.checked })}
          />
          Solo productos disponibles
        </label>
      </div>
      
      {/* Grid de productos */}
      <div className="products-grid">
        {data?.results.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
      
      {/* Paginación */}
      {data && (
        <div className="pagination">
          {data.previous && (
            <button onClick={() => setFilters({ ...filters, page: (filters.page || 1) - 1 })}>
              Anterior
            </button>
          )}
          {data.next && (
            <button onClick={() => setFilters({ ...filters, page: (filters.page || 1) + 1 })}>
              Siguiente
            </button>
          )}
        </div>
      )}
    </div>
  );
};
```

---

### 2. ProductDetailPage

**Ubicación**: `pages/marketplace/ProductDetailPage.tsx`

```typescript
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useProduct, useAddToCart } from '@/hooks/useMarketplace';
import { VariantSelector } from '@/components/marketplace/VariantSelector';
import { ProductVariant } from '@/types/marketplace';

export const ProductDetailPage = () => {
  const { productId } = useParams<{ productId: string }>();
  const { data: product, isLoading } = useProduct(productId!);
  const addToCart = useAddToCart();
  
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(null);
  const [quantity, setQuantity] = useState(1);

  if (isLoading) return <div>Cargando...</div>;
  if (!product) return <div>Producto no encontrado</div>;

  const handleAddToCart = () => {
    if (!selectedVariant) {
      alert('Selecciona una presentación');
      return;
    }
    
    addToCart.mutate({
      variant_id: selectedVariant.id,
      quantity
    }, {
      onSuccess: () => {
        alert('Producto agregado al carrito');
      },
      onError: (error: any) => {
        alert(error.response?.data?.error || 'Error al agregar al carrito');
      }
    });
  };

  return (
    <div className="product-detail-page">
      <div className="product-images">
        {product.images?.map((img, idx) => (
          <img key={idx} src={img.image} alt={img.alt_text} />
        ))}
      </div>
      
      <div className="product-info">
        <h1>{product.name}</h1>
        <p>{product.description}</p>
        
        {product.variants && (
          <VariantSelector
            variants={product.variants}
            selectedVariant={selectedVariant}
            onSelectVariant={setSelectedVariant}
          />
        )}
        
        <div className="quantity-selector">
          <label>Cantidad:</label>
          <input
            type="number"
            min="1"
            max={selectedVariant?.stock || 1}
            value={quantity}
            onChange={(e) => setQuantity(parseInt(e.target.value))}
          />
        </div>
        
        <button 
          onClick={handleAddToCart}
          disabled={!selectedVariant || selectedVariant.stock === 0 || addToCart.isPending}
        >
          {addToCart.isPending ? 'Agregando...' : 'Agregar al carrito'}
        </button>
      </div>
    </div>
  );
};
```

---

### 3. CartPage

**Ubicación**: `pages/marketplace/CartPage.tsx`

```typescript
import { useCart } from '@/hooks/useMarketplace';
import { CartItemCard } from '@/components/marketplace/CartItemCard';
import { Link } from 'react-router-dom';

export const CartPage = () => {
  const { data: cart, isLoading } = useCart();

  if (isLoading) return <div>Cargando carrito...</div>;
  if (!cart || cart.items.length === 0) {
    return (
      <div className="empty-cart">
        <h2>Tu carrito está vacío</h2>
        <Link to="/marketplace/products">Ver productos</Link>
      </div>
    );
  }

  return (
    <div className="cart-page">
      <h1>Mi Carrito</h1>
      
      <div className="cart-items">
        {cart.items.map((item) => (
          <CartItemCard key={item.id} item={item} />
        ))}
      </div>
      
      <div className="cart-summary">
        <h3>Resumen</h3>
        <div className="summary-line">
          <span>Subtotal:</span>
          <span>${parseFloat(cart.total).toLocaleString('es-CO')}</span>
        </div>
        <div className="summary-line total">
          <span>Total:</span>
          <span>${parseFloat(cart.total).toLocaleString('es-CO')}</span>
        </div>
        
        <Link to="/marketplace/checkout" className="btn-checkout">
          Proceder al pago
        </Link>
      </div>
    </div>
  );
};
```

---

### 4. CheckoutPage

**Ubicación**: `pages/marketplace/CheckoutPage.tsx`

```typescript
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart, useCheckout } from '@/hooks/useMarketplace';
import { DeliveryOption } from '@/types/marketplace';

export const CheckoutPage = () => {
  const navigate = useNavigate();
  const { data: cart } = useCart();
  const checkout = useCheckout();
  
  const [deliveryOption, setDeliveryOption] = useState<DeliveryOption>('PICKUP');
  const [deliveryAddress, setDeliveryAddress] = useState('');

  const handleCheckout = () => {
    const data: any = { delivery_option: deliveryOption };
    
    if (deliveryOption === 'DELIVERY') {
      if (!deliveryAddress || deliveryAddress.length < 15) {
        alert('Por favor ingresa una dirección válida');
        return;
      }
      data.delivery_address = deliveryAddress;
    }
    
    checkout.mutate(data, {
      onSuccess: (response) => {
        // Redirigir a Wompi
        const { payment } = response;
        const wompiUrl = `https://checkout.wompi.co/p/?` +
          `public-key=${payment.publicKey}&` +
          `currency=${payment.currency}&` +
          `amount-in-cents=${payment.amountInCents}&` +
          `reference=${payment.reference}&` +
          `signature:integrity=${payment.signatureIntegrity}&` +
          `redirect-url=${encodeURIComponent(payment.redirectUrl)}`;
        
        window.location.href = wompiUrl;
      },
      onError: (error: any) => {
        alert(error.response?.data?.error || 'Error al procesar el pago');
      }
    });
  };

  return (
    <div className="checkout-page">
      <h1>Checkout</h1>
      
      {/* Resumen del carrito */}
      <div className="order-summary">
        <h3>Resumen de tu orden</h3>
        {cart?.items.map((item) => (
          <div key={item.id} className="summary-item">
            <span>{item.product.name} - {item.variant.name} x{item.quantity}</span>
            <span>${parseFloat(item.subtotal).toLocaleString('es-CO')}</span>
          </div>
        ))}
        <div className="summary-total">
          <strong>Total:</strong>
          <strong>${parseFloat(cart?.total || '0').toLocaleString('es-CO')}</strong>
        </div>
      </div>
      
      {/* Opciones de entrega */}
      <div className="delivery-options">
        <h3>Opción de entrega</h3>
        
        <label>
          <input
            type="radio"
            value="PICKUP"
            checked={deliveryOption === 'PICKUP'}
            onChange={(e) => setDeliveryOption(e.target.value as DeliveryOption)}
          />
          Recogida en local
        </label>
        
        <label>
          <input
            type="radio"
            value="DELIVERY"
            checked={deliveryOption === 'DELIVERY'}
            onChange={(e) => setDeliveryOption(e.target.value as DeliveryOption)}
          />
          Envío a domicilio
        </label>
        
        {deliveryOption === 'DELIVERY' && (
          <div className="delivery-address">
            <label>Dirección de entrega:</label>
            <input
              type="text"
              placeholder="Calle 123 #45-67, Apartamento 801, Bogotá"
              value={deliveryAddress}
              onChange={(e) => setDeliveryAddress(e.target.value)}
            />
            <p className="help-text">
              Debe incluir tipo de vía, nomenclatura y barrio
            </p>
          </div>
        )}
      </div>
      
      <button 
        onClick={handleCheckout}
        disabled={checkout.isPending}
        className="btn-pay"
      >
        {checkout.isPending ? 'Procesando...' : 'Pagar con Wompi'}
      </button>
    </div>
  );
};
```

---

### 5. OrderResultPage

**Ubicación**: `pages/marketplace/OrderResultPage.tsx`

```typescript
import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useOrders } from '@/hooks/useMarketplace';

export const OrderResultPage = () => {
  const [searchParams] = useSearchParams();
  const transactionId = searchParams.get('id');
  const { data: orders } = useOrders();
  const [order, setOrder] = useState<any>(null);

  useEffect(() => {
    // Esperar 3 segundos para que el webhook procese
    const timer = setTimeout(() => {
      // Buscar la orden por transaction_id
      const foundOrder = orders?.results.find(
        (o) => o.id === transactionId || o.wompi_transaction_id === transactionId
      );
      setOrder(foundOrder);
    }, 3000);

    return () => clearTimeout(timer);
  }, [transactionId, orders]);

  if (!order) {
    return <div>Verificando estado del pago...</div>;
  }

  const isSuccess = order.status === 'PAID' || order.status === 'PREPARING';

  return (
    <div className="order-result-page">
      {isSuccess ? (
        <>
          <h1>✅ ¡Pago exitoso!</h1>
          <p>Tu orden ha sido creada correctamente</p>
          <div className="order-details">
            <p><strong>Número de orden:</strong> {order.id}</p>
            <p><strong>Total:</strong> ${parseFloat(order.total_amount).toLocaleString('es-CO')}</p>
            <p><strong>Estado:</strong> {order.status}</p>
          </div>
          <Link to="/marketplace/orders">Ver mis órdenes</Link>
        </>
      ) : (
        <>
          <h1>❌ Error en el pago</h1>
          <p>No se pudo procesar tu pago</p>
          <Link to="/marketplace/cart">Volver al carrito</Link>
        </>
      )}
    </div>
  );
};
```

---

## 🔄 Flujos de Usuario

### Flujo 1: Compra de Producto

```
1. Usuario navega a /marketplace/products
2. Aplica filtros (opcional)
3. Click en producto → /marketplace/products/{id}
4. Selecciona variante
5. Selecciona cantidad
6. Click "Agregar al carrito"
7. Ve icono de carrito actualizado
8. Click en carrito → /marketplace/cart
9. Revisa items
10. Click "Proceder al pago" → /marketplace/checkout
11. Selecciona opción de entrega
12. Ingresa dirección (si aplica)
13. Click "Pagar con Wompi"
14. Redirige a Wompi
15. Completa pago
16. Redirige a /marketplace/payment-result
17. Ve confirmación
```

---

## 💳 Integración con Wompi

### Método: Redirect Manual

```typescript
// En CheckoutPage.tsx
const redirectToWompi = (paymentData: WompiPaymentData) => {
  const wompiUrl = `https://checkout.wompi.co/p/?` +
    `public-key=${paymentData.publicKey}&` +
    `currency=${paymentData.currency}&` +
    `amount-in-cents=${paymentData.amountInCents}&` +
    `reference=${paymentData.reference}&` +
    `signature:integrity=${paymentData.signatureIntegrity}&` +
    `redirect-url=${encodeURIComponent(paymentData.redirectUrl)}`;
  
  window.location.href = wompiUrl;
};
```

---

## ⚠️ Manejo de Errores

### Códigos de Error del Backend

| Código | Descripción | Acción Frontend |
|--------|-------------|-----------------|
| `MKT-CART-LIMIT` | Límite de 50 productos | Mostrar mensaje, no permitir agregar más |
| `MKT-QUANTITY-LIMIT` | Máximo 100 unidades | Limitar input de cantidad |
| `MKT-STOCK-CART` | Stock insuficiente | Mostrar stock disponible, ajustar cantidad |
| `MKT-PAYMENT-ERROR` | Error al iniciar pago | Mostrar error, permitir reintentar |

---

## ✅ Checklist de Implementación

### Tipos y Configuración
- [ ] Crear `types/marketplace.ts`
- [ ] Crear `hooks/useMarketplace.ts`
- [ ] Configurar rutas en React Router

### Componentes
- [ ] `ProductCard`
- [ ] `CartItemCard`
- [ ] `VariantSelector`
- [ ] `CartIcon` (badge con cantidad)

### Páginas
- [ ] `ProductListPage`
- [ ] `ProductDetailPage`
- [ ] `CartPage`
- [ ] `CheckoutPage`
- [ ] `OrderResultPage`
- [ ] `OrderHistoryPage`

### Funcionalidades
- [ ] Filtros de productos
- [ ] Búsqueda de productos
- [ ] Agregar al carrito
- [ ] Actualizar cantidad
- [ ] Eliminar del carrito
- [ ] Checkout con opciones de entrega
- [ ] Integración Wompi
- [ ] Ver historial de órdenes

---

**Última actualización**: 13 de Diciembre, 2024  
**Estado**: ✅ Documentación completa lista para implementación
