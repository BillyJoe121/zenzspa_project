# Sistema VIP - Referencia Rápida

## 🚀 Quick Start

### Endpoints Esenciales

```typescript
// Obtener datos del usuario (incluye campos VIP)
GET /api/v1/users/me/

// Obtener precio VIP y configuración
GET /api/v1/settings/

// Iniciar suscripción VIP
POST /api/v1/finances/payments/vip-subscription/initiate/

// Cancelar auto-renovación
POST /api/v1/spa/vip/cancel-subscription/

// Historial de pagos
GET /api/v1/finances/payments/my/
```

---

## 📊 Datos del Usuario VIP

```typescript
interface User {
  role: 'CLIENT' | 'VIP' | 'STAFF' | 'ADMIN';
  vip_expires_at: string | null;       // "2025-01-13"
  vip_active_since: string | null;     // "2024-10-13"
  vip_auto_renew: boolean;             // true/false
  vip_failed_payments: number;         // 0-3
  is_vip: boolean;                     // Calculado por backend
}
```

---

## 💰 Flujo de Compra VIP

```javascript
// 1. Iniciar pago
const response = await fetch('/api/v1/finances/payments/vip-subscription/initiate/', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` }
});
const wompiData = await response.json();

// 2. Abrir widget de Wompi
const checkout = new WidgetCheckout({
  currency: wompiData.currency,
  amountInCents: wompiData.amountInCents,
  reference: wompiData.reference,
  publicKey: wompiData.publicKey,
  redirectUrl: wompiData.redirectUrl,
  signature: { integrity: wompiData.signatureIntegrity }
});
checkout.open();

// 3. Wompi redirige a: /vip/payment-result?id=TRANSACTION_ID
// 4. Backend procesa webhook y actualiza usuario a VIP
```

---

## 🎨 Componentes Clave

### 1. Mostrar Precio VIP en Servicios

```tsx
function ServicePrice({ service, isVip }) {
  const price = isVip && service.vip_price
    ? service.vip_price
    : service.price;

  return (
    <div>
      {isVip && service.vip_price && (
        <span className="original">${service.price}</span>
      )}
      <span className="price">${price}</span>
      {isVip && service.vip_price && (
        <span className="badge">PRECIO VIP</span>
      )}
    </div>
  );
}
```

### 2. Badge VIP

```tsx
function VIPBadge({ user }) {
  if (!user.is_vip) return null;
  return <span className="vip-badge">👑 VIP</span>;
}
```

### 3. Control de Auto-Renovación

```tsx
async function cancelAutoRenewal() {
  await fetch('/api/v1/spa/vip/cancel-subscription/', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  // Actualizar user.vip_auto_renew = false localmente
}
```

---

## 📅 Cálculos Útiles

```typescript
// Días hasta expiración
function daysUntilExpiration(user: User): number {
  const expiry = new Date(user.vip_expires_at!);
  const today = new Date();
  return Math.ceil((expiry - today) / (1000 * 60 * 60 * 24));
}

// Progreso de lealtad (para recompensas)
function loyaltyProgress(user: User, requiredMonths: number) {
  const since = new Date(user.vip_active_since!);
  const today = new Date();
  const months = (today.getFullYear() - since.getFullYear()) * 12
               + (today.getMonth() - since.getMonth());

  return {
    current: months % requiredMonths,
    total: requiredMonths,
    percentage: ((months % requiredMonths) / requiredMonths) * 100
  };
}

// Debe mostrar advertencia de expiración?
function shouldWarn(user: User): boolean {
  if (!user.is_vip || user.vip_auto_renew) return false;
  const days = daysUntilExpiration(user);
  return days <= 7 && days > 0;
}
```

---

## 🎯 Estados Posibles

| Estado | role | is_vip | vip_auto_renew | Acción Permitida |
|--------|------|--------|----------------|------------------|
| Cliente | CLIENT | false | false | ✅ Comprar VIP |
| VIP Activo | VIP | true | true | ✅ Cancelar renovación |
| VIP sin Renovar | VIP | true | false | ✅ Comprar de nuevo |
| VIP Expirado | CLIENT | false | false | ✅ Comprar VIP |

---

## ⚠️ Validaciones

```typescript
// Puede comprar VIP?
const canBuy = !user.is_vip;

// Puede cancelar renovación?
const canCancel = user.is_vip && user.vip_auto_renew;

// Tiene fallos de pago?
const hasFailures = user.vip_failed_payments > 0;

// Próximo a expirar?
const nearExpiry = daysUntilExpiration(user) <= 7;
```

---

## 🔔 Notificaciones

```typescript
// Tipos de eventos VIP
type VIPEvent =
  | 'VIP_RENEWAL_FAILED'        // Falló cobro automático
  | 'VIP_MEMBERSHIP_EXPIRED'    // Membresía expiró
  | 'LOYALTY_REWARD_ISSUED';    // Recibió recompensa
```

---

## 📱 Páginas Necesarias

1. **/vip** - Landing page con info y botón de suscripción
2. **/vip/membership** - Panel de membresía (solo VIP)
3. **/vip/payment-result** - Resultado del pago

---

## 🛠️ Configuración Widget Wompi

```html
<!-- En <head> -->
<script src="https://checkout.wompi.co/widget.js"></script>
```

```typescript
// Variables de entorno
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WOMPI_REDIRECT_URL=http://localhost:3000/vip/payment-result
```

---

## 📚 Documentación Completa

Ver: [docs/VIP_SYSTEM_FRONTEND_GUIDE.md](./VIP_SYSTEM_FRONTEND_GUIDE.md)

- Endpoints detallados con ejemplos
- Componentes completos con código
- Flujos paso a paso
- Integración Wompi completa
- Casos de error y validaciones

---

## ✅ Checklist de Implementación

- [ ] Página VIP landing
- [ ] Página panel de membresía
- [ ] Página resultado de pago
- [ ] Componente ServiceCard con precios VIP
- [ ] Componente VIPBadge
- [ ] Integración widget Wompi
- [ ] Cancelar auto-renovación
- [ ] Mostrar advertencias de expiración
- [ ] Historial de pagos
- [ ] Barra de progreso de lealtad

---

**Para dudas específicas, revisa la [Guía Completa](./VIP_SYSTEM_FRONTEND_GUIDE.md)**
