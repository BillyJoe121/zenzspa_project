# 🎯 Acceso a Precios VIP desde el Frontend

**Fecha**: 13 de Diciembre, 2024  
**Versión**: 1.0

---

## 📋 Resumen Ejecutivo

### ¿Dónde se calculan los precios VIP?
**✅ Los precios VIP se calculan y almacenan en el BACKEND**

- Los precios VIP están **pre-calculados** en la base de datos
- El frontend **NO calcula** descuentos, solo los **muestra**
- El backend aplica automáticamente el precio correcto según el rol del usuario

---

## 🛍️ 1. SERVICIOS (Spa)

### Backend - Modelo

```python
# spa/models/appointment.py
class Service(BaseModel):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Optional discounted price for VIP members.'
    )
    # ... otros campos
```

### API - Endpoint

```
GET /api/v1/services/
```

**Respuesta**:
```json
{
  "results": [
    {
      "id": "uuid-123",
      "name": "Hidra Facial",
      "description": "Tratamiento facial profundo...",
      "duration": 90,
      "price": "180000.00",        // ← Precio regular
      "vip_price": "153000.00",    // ← Precio VIP (15% descuento)
      "category": "uuid-cat",
      "category_name": "Faciales",
      "is_active": true
    },
    {
      "id": "uuid-456",
      "name": "Pediluvio",
      "price": "80000.00",
      "vip_price": "68000.00",     // ← Precio VIP
      // ...
    }
  ]
}
```

### Frontend - TypeScript Types

```typescript
// types/service.ts
export interface Service {
  id: string;
  name: string;
  description: string;
  duration: number;
  price: string;              // "180000.00"
  vip_price: string | null;   // "153000.00" o null
  category: string;
  category_name: string;
  is_active: boolean;
}
```

### Frontend - Hook para Obtener Servicios

```typescript
// hooks/useServices.ts
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { Service } from '@/types/service';

export const useServices = () => {
  return useQuery({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await api.get<{ results: Service[] }>('/api/v1/services/');
      return response.data.results;
    },
  });
};

// Uso:
const { data: services, isLoading } = useServices();
```

### Frontend - Componente ServiceCard

```tsx
// components/ServiceCard.tsx
import { Service } from '@/types/service';
import { useAuth } from '@/hooks/useAuth';

interface ServiceCardProps {
  service: Service;
}

export const ServiceCard = ({ service }: ServiceCardProps) => {
  const { user } = useAuth();
  
  // Determinar si el usuario es VIP
  const isVIP = user?.role === 'VIP';
  
  // Verificar si el servicio tiene precio VIP
  const hasVIPPrice = service.vip_price !== null;
  
  // Calcular ahorro
  const savings = hasVIPPrice 
    ? parseFloat(service.price) - parseFloat(service.vip_price)
    : 0;

  return (
    <div className="service-card">
      <h3>{service.name}</h3>
      <p>{service.description}</p>
      <p>Duración: {service.duration} min</p>
      
      {/* CASO 1: Usuario VIP con precio VIP disponible */}
      {isVIP && hasVIPPrice ? (
        <div className="vip-pricing">
          <span className="original-price line-through text-gray-500">
            ${parseFloat(service.price).toLocaleString('es-CO')}
          </span>
          <span className="vip-price text-2xl font-bold text-gold">
            ${parseFloat(service.vip_price).toLocaleString('es-CO')}
          </span>
          <span className="savings text-green-600">
            Ahorras ${savings.toLocaleString('es-CO')}
          </span>
          <span className="vip-badge">👑 Precio VIP</span>
        </div>
      ) : hasVIPPrice ? (
        /* CASO 2: Usuario NO VIP, mostrar promoción */
        <div className="regular-pricing">
          <span className="price text-2xl font-bold">
            ${parseFloat(service.price).toLocaleString('es-CO')}
          </span>
          <div className="vip-promotion bg-gold/10 p-3 rounded mt-2">
            <p className="text-sm">
              💎 Precio VIP: ${parseFloat(service.vip_price).toLocaleString('es-CO')}
            </p>
            <p className="text-xs text-gray-600">
              Ahorra ${savings.toLocaleString('es-CO')} siendo VIP
            </p>
            <Link to="/vip" className="btn-vip">
              Hazte VIP
            </Link>
          </div>
        </div>
      ) : (
        /* CASO 3: Sin precio VIP */
        <span className="price text-2xl font-bold">
          ${parseFloat(service.price).toLocaleString('es-CO')}
        </span>
      )}
      
      <button className="btn-reserve">Reservar</button>
    </div>
  );
};
```

---

## 📦 2. PRODUCTOS (Marketplace)

### Backend - Modelo

```python
# marketplace/models.py
class ProductVariant(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)  # "50ml", "100ml"
    sku = models.CharField(max_length=60, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vip_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio para VIPs"
    )
    stock = models.PositiveIntegerField(default=0)
    # ... otros campos
```

### API - Endpoint de Productos

```
GET /api/v1/marketplace/products/
```

**Respuesta**:
```json
{
  "results": [
    {
      "id": "uuid-product-1",
      "name": "Crema Hidratante Premium",
      "price": "85000.00",         // ← Precio mínimo de variantes
      "vip_price": "72250.00",     // ← Precio VIP mínimo (15% descuento)
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

### API - Endpoint de Detalle de Producto

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
      "vip_price": "72250.00",    // ← Precio VIP por variante
      "stock": 25
    },
    {
      "id": "uuid-var-2",
      "sku": "CREMA-100ML",
      "name": "100ml",
      "price": "150000.00",
      "vip_price": "127500.00",   // ← Precio VIP por variante
      "stock": 20
    }
  ],
  "average_rating": 4.5,
  "review_count": 12
}
```

### Frontend - TypeScript Types

```typescript
// types/product.ts
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
  description: string;
  price: string;              // Precio mínimo de variantes
  vip_price: string | null;   // Precio VIP mínimo
  stock: number;
  main_image: {
    image: string;
    is_primary: boolean;
    alt_text: string;
  } | null;
  variants?: ProductVariant[];
  average_rating?: number;
  review_count?: number;
}
```

### Frontend - Hook para Obtener Productos

```typescript
// hooks/useProducts.ts
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import type { Product } from '@/types/product';

export const useProducts = () => {
  return useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const response = await api.get<{ results: Product[] }>(
        '/api/v1/marketplace/products/'
      );
      return response.data.results;
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
```

### Frontend - Componente ProductCard

```tsx
// components/ProductCard.tsx
import { Product } from '@/types/product';
import { useAuth } from '@/hooks/useAuth';

interface ProductCardProps {
  product: Product;
}

export const ProductCard = ({ product }: ProductCardProps) => {
  const { user } = useAuth();
  const isVIP = user?.role === 'VIP';
  const hasVIPPrice = product.vip_price !== null;
  
  const savings = hasVIPPrice
    ? parseFloat(product.price) - parseFloat(product.vip_price)
    : 0;

  return (
    <div className="product-card">
      {product.main_image && (
        <img 
          src={product.main_image.image} 
          alt={product.main_image.alt_text}
          className="product-image"
        />
      )}
      
      <h3>{product.name}</h3>
      
      {/* Precios */}
      {isVIP && hasVIPPrice ? (
        <div className="vip-pricing">
          <span className="original-price line-through">
            Desde ${parseFloat(product.price).toLocaleString('es-CO')}
          </span>
          <span className="vip-price text-xl font-bold text-gold">
            Desde ${parseFloat(product.vip_price).toLocaleString('es-CO')}
          </span>
          <span className="savings text-sm text-green-600">
            Ahorras desde ${savings.toLocaleString('es-CO')}
          </span>
        </div>
      ) : hasVIPPrice ? (
        <div className="regular-pricing">
          <span className="price text-xl font-bold">
            Desde ${parseFloat(product.price).toLocaleString('es-CO')}
          </span>
          <p className="vip-promo text-sm text-gold">
            💎 Precio VIP desde ${parseFloat(product.vip_price).toLocaleString('es-CO')}
          </p>
        </div>
      ) : (
        <span className="price text-xl font-bold">
          Desde ${parseFloat(product.price).toLocaleString('es-CO')}
        </span>
      )}
      
      <Link to={`/marketplace/products/${product.id}`}>
        Ver detalles
      </Link>
    </div>
  );
};
```

### Frontend - Selector de Variantes

```tsx
// components/ProductDetail.tsx
import { useState } from 'react';
import { Product, ProductVariant } from '@/types/product';
import { useAuth } from '@/hooks/useAuth';

interface ProductDetailProps {
  product: Product;
}

export const ProductDetail = ({ product }: ProductDetailProps) => {
  const { user } = useAuth();
  const isVIP = user?.role === 'VIP';
  
  const [selectedVariant, setSelectedVariant] = useState<ProductVariant | null>(
    product.variants?.[0] || null
  );

  const currentPrice = selectedVariant?.price || product.price;
  const currentVIPPrice = selectedVariant?.vip_price || product.vip_price;
  const hasVIPPrice = currentVIPPrice !== null;
  
  const savings = hasVIPPrice
    ? parseFloat(currentPrice) - parseFloat(currentVIPPrice)
    : 0;

  return (
    <div className="product-detail">
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      
      {/* Selector de Variantes */}
      {product.variants && product.variants.length > 0 && (
        <div className="variants-selector">
          <label>Presentación:</label>
          <div className="variants-grid">
            {product.variants.map((variant) => (
              <button
                key={variant.id}
                onClick={() => setSelectedVariant(variant)}
                className={`variant-btn ${
                  selectedVariant?.id === variant.id ? 'active' : ''
                }`}
              >
                {variant.name}
              </button>
            ))}
          </div>
        </div>
      )}
      
      {/* Precios de la variante seleccionada */}
      <div className="pricing-section">
        {isVIP && hasVIPPrice ? (
          <>
            <span className="original-price line-through text-gray-500">
              ${parseFloat(currentPrice).toLocaleString('es-CO')}
            </span>
            <span className="vip-price text-3xl font-bold text-gold">
              ${parseFloat(currentVIPPrice).toLocaleString('es-CO')}
            </span>
            <span className="savings-badge bg-green-100 text-green-800 px-3 py-1 rounded">
              Ahorras ${savings.toLocaleString('es-CO')} (15%)
            </span>
            <span className="vip-badge">👑 Tu precio VIP</span>
          </>
        ) : hasVIPPrice ? (
          <>
            <span className="price text-3xl font-bold">
              ${parseFloat(currentPrice).toLocaleString('es-CO')}
            </span>
            <div className="vip-promotion bg-gold/10 p-4 rounded mt-3">
              <p className="font-semibold">
                💎 Precio VIP: ${parseFloat(currentVIPPrice).toLocaleString('es-CO')}
              </p>
              <p className="text-sm text-gray-600">
                Ahorra ${savings.toLocaleString('es-CO')} (15%) siendo miembro VIP
              </p>
              <Link to="/vip" className="btn-vip mt-2">
                Hazte VIP por $39,900/mes
              </Link>
            </div>
          </>
        ) : (
          <span className="price text-3xl font-bold">
            ${parseFloat(currentPrice).toLocaleString('es-CO')}
          </span>
        )}
      </div>
      
      <button 
        className="btn-add-to-cart"
        disabled={!selectedVariant || selectedVariant.stock === 0}
      >
        {selectedVariant?.stock === 0 ? 'Agotado' : 'Agregar al carrito'}
      </button>
    </div>
  );
};
```

---

## 🛒 3. CARRITO DE COMPRAS

### Backend - Cálculo Automático

El backend **calcula automáticamente** el precio correcto en el carrito:

```python
# marketplace/serializers.py (línea 141-148)
def get_subtotal(self, obj):
    # Calcula el subtotal basado en el rol del usuario
    request = self.context.get('request')
    user = getattr(request, 'user', None)
    price = obj.variant.price
    if user and getattr(user, "is_vip", False) and obj.variant.vip_price:
        price = obj.variant.vip_price
    return obj.quantity * price
```

### API - Endpoint del Carrito

```
GET /api/v1/marketplace/cart/
```

**Respuesta para Usuario VIP**:
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
      "subtotal": "144500.00"    // ← 2 × 72250 (precio VIP aplicado)
    }
  ],
  "total": "144500.00"           // ← Total con precios VIP
}
```

**Respuesta para Usuario Regular**:
```json
{
  // ... mismo carrito
  "items": [
    {
      // ... mismo item
      "subtotal": "170000.00"    // ← 2 × 85000 (precio regular)
    }
  ],
  "total": "170000.00"           // ← Total con precios regulares
}
```

### Frontend - Componente Cart

```tsx
// components/Cart.tsx
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

interface CartItem {
  id: string;
  product: { id: string; name: string };
  variant: {
    id: string;
    sku: string;
    name: string;
    price: string;
    vip_price: string | null;
    stock: number;
  };
  quantity: number;
  subtotal: string;  // ← Ya calculado por el backend
}

interface Cart {
  id: string;
  items: CartItem[];
  total: string;     // ← Ya calculado por el backend
}

export const Cart = () => {
  const { data: cart } = useQuery({
    queryKey: ['cart'],
    queryFn: async () => {
      const response = await api.get<Cart>('/api/v1/marketplace/cart/');
      return response.data;
    },
  });

  if (!cart || cart.items.length === 0) {
    return <div>Tu carrito está vacío</div>;
  }

  return (
    <div className="cart">
      <h2>Mi Carrito</h2>
      
      {cart.items.map((item) => (
        <div key={item.id} className="cart-item">
          <h3>{item.product.name}</h3>
          <p>Presentación: {item.variant.name}</p>
          <p>Cantidad: {item.quantity}</p>
          
          {/* El subtotal ya viene calculado del backend */}
          <p className="subtotal">
            Subtotal: ${parseFloat(item.subtotal).toLocaleString('es-CO')}
          </p>
        </div>
      ))}
      
      <div className="cart-total">
        {/* El total ya viene calculado del backend */}
        <h3>Total: ${parseFloat(cart.total).toLocaleString('es-CO')}</h3>
      </div>
      
      <button className="btn-checkout">
        Proceder al pago
      </button>
    </div>
  );
};
```

---

## ⚙️ 4. CONFIGURACIÓN GLOBAL VIP

### API - Endpoint de Configuración

```
GET /api/v1/settings/
```

**Respuesta**:
```json
{
  "vip_monthly_price": "39900.00",
  "loyalty_months_required": 3,
  "loyalty_voucher_service": "uuid-service",
  "loyalty_voucher_service_name": "Pediluvio",
  "credit_expiration_days": 365,
  "advance_payment_percentage": 40
}
```

### Frontend - Hook para Configuración

```typescript
// hooks/useSettings.ts
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';

interface GlobalSettings {
  vip_monthly_price: string;
  loyalty_months_required: number;
  loyalty_voucher_service_name: string;
  credit_expiration_days: number;
  advance_payment_percentage: number;
}

export const useSettings = () => {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await api.get<GlobalSettings>('/api/v1/settings/');
      return response.data;
    },
    staleTime: 1000 * 60 * 60, // 1 hora (raramente cambia)
  });
};

// Uso:
const { data: settings } = useSettings();
const vipPrice = settings?.vip_monthly_price; // "39900.00"
```

---

## 📊 5. RESUMEN: ¿Qué hace el Frontend?

### ✅ El Frontend SÍ hace:

1. **Obtener datos** de la API (servicios, productos, carrito)
2. **Mostrar precios** según el rol del usuario
3. **Calcular ahorros** para mostrar al usuario (solo UI)
4. **Renderizar badges** VIP y promociones
5. **Formatear precios** para visualización (ej: `toLocaleString('es-CO')`)

### ❌ El Frontend NO hace:

1. **Calcular descuentos** (ya vienen calculados del backend)
2. **Aplicar precios VIP** (el backend lo hace automáticamente)
3. **Validar roles** para precios (el backend lo maneja)
4. **Modificar precios** (son read-only desde la API)

---

## 🔐 6. SEGURIDAD

### Backend - Validación de Roles

El backend **siempre valida** el rol del usuario antes de aplicar precios:

```python
# Ejemplo en marketplace/serializers.py
def get_subtotal(self, obj):
    request = self.context.get('request')
    user = getattr(request, 'user', None)
    price = obj.variant.price
    
    # ✅ Validación en el backend
    if user and getattr(user, "is_vip", False) and obj.variant.vip_price:
        price = obj.variant.vip_price
    
    return obj.quantity * price
```

### Frontend - Solo Visualización

El frontend **nunca debe confiar** en sus propios cálculos para pagos:

```typescript
// ❌ INCORRECTO: Calcular precio en frontend para pago
const finalPrice = user.is_vip ? service.vip_price : service.price;
await api.post('/payments/', { amount: finalPrice }); // ¡NO!

// ✅ CORRECTO: El backend calcula el precio
await api.post('/appointments/', { service_ids: [serviceId] });
// El backend automáticamente aplica el precio correcto
```

---

## 📝 7. CHECKLIST DE IMPLEMENTACIÓN

### Para Servicios

- [ ] Crear tipo `Service` en TypeScript
- [ ] Crear hook `useServices()`
- [ ] Crear componente `ServiceCard` con lógica VIP
- [ ] Mostrar precio regular tachado para VIPs
- [ ] Mostrar promoción VIP para no-VIPs
- [ ] Calcular y mostrar ahorro en UI

### Para Productos

- [ ] Crear tipos `Product` y `ProductVariant` en TypeScript
- [ ] Crear hooks `useProducts()` y `useProduct(id)`
- [ ] Crear componente `ProductCard` con lógica VIP
- [ ] Crear selector de variantes con precios VIP
- [ ] Mostrar precio VIP por variante seleccionada
- [ ] Integrar con carrito (precios ya calculados)

### Para Carrito

- [ ] Crear tipo `Cart` y `CartItem` en TypeScript
- [ ] Crear hook `useCart()`
- [ ] Mostrar subtotales (ya calculados por backend)
- [ ] Mostrar total (ya calculado por backend)
- [ ] **NO** recalcular precios en frontend

---

## 🎯 8. EJEMPLO COMPLETO: Flujo de Compra

```typescript
// 1. Usuario ve servicio
const { data: services } = useServices();
const service = services[0];
// service.price = "180000.00"
// service.vip_price = "153000.00"

// 2. Usuario reserva cita
await api.post('/api/v1/appointments/', {
  service_ids: [service.id],
  start_time: '2024-12-20T10:00:00Z',
  staff_member: staffId
});

// 3. Backend crea cita con precio correcto
// Si user.role === 'VIP':
//   appointment.price_at_purchase = service.vip_price  // 153000
// Si user.role === 'CLIENT':
//   appointment.price_at_purchase = service.price      // 180000

// 4. Usuario paga
// El backend usa appointment.price_at_purchase
// El frontend NO necesita saber qué precio se aplicó
```

---

**Última actualización**: 13 de Diciembre, 2024  
**Autor**: Sistema StudioZens  
**Estado**: ✅ Documentación Completa
