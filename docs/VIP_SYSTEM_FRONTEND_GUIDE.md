# Sistema VIP - Guía Completa para Frontend

## 📋 Índice

1. [Resumen del Sistema](#resumen-del-sistema)
2. [Modelos y Estructura de Datos](#modelos-y-estructura-de-datos)
3. [API Endpoints](#api-endpoints)
4. [Flujos de Usuario](#flujos-de-usuario)
5. [Componentes Sugeridos](#componentes-sugeridos)
6. [Integración de Pagos (Wompi)](#integración-de-pagos-wompi)
7. [Estados y Permisos](#estados-y-permisos)
8. [Notificaciones](#notificaciones)
9. [Ejemplos de Código](#ejemplos-de-código)

---

## 1. Resumen del Sistema

El sistema VIP de StudioZens es una **plataforma de suscripción recurrente** que ofrece:

### ✨ Características Principales

- **Membresía Mensual**: Suscripción con precio configurable
- **Precios Especiales**: Descuentos VIP en servicios del spa
- **Renovación Automática**: Cobro automático mensual con tarjeta guardada
- **Recompensas de Lealtad**: Vouchers gratuitos después de N meses continuos
- **Gestión de Suscripción**: Cancelar auto-renovación, historial de pagos
- **Sistema de Intentos**: 3 intentos de cobro antes de cancelar automáticamente

### 🎯 Beneficios para Usuarios VIP

1. **Precios Reducidos**: Acceso a `vip_price` en servicios (menor que `price`)
2. **Recompensas Automáticas**: Servicio gratuito cada 3 meses (configurable)
3. **Prioridad**: Rol VIP con acceso especial

---

## 2. Modelos y Estructura de Datos

### 2.1 Usuario VIP (`CustomUser`)

**Campos VIP en el modelo de usuario:**

```typescript
interface User {
  id: number;
  phone_number: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'CLIENT' | 'VIP' | 'STAFF' | 'ADMIN';

  // Campos VIP específicos
  vip_expires_at: string | null;        // Fecha de expiración (YYYY-MM-DD)
  vip_active_since: string | null;      // Inicio de membresía continua
  vip_auto_renew: boolean;              // Si tiene auto-renovación activa
  vip_failed_payments: number;          // Contador de fallos (max 3)

  // Propiedad calculada (backend)
  is_vip: boolean;                      // role === 'VIP' && !expired
}
```

**Endpoint para obtener datos del usuario actual:**
```
GET /api/v1/users/me/
```

**Respuesta:**
```json
{
  "id": 123,
  "phone_number": "+573001234567",
  "email": "user@example.com",
  "first_name": "Juan",
  "last_name": "Pérez",
  "role": "VIP",
  "vip_expires_at": "2025-01-13",
  "vip_active_since": "2024-10-13",
  "vip_auto_renew": true,
  "vip_failed_payments": 0,
  "is_vip": true
}
```

---

### 2.2 Configuración Global VIP

**Endpoint:**
```
GET /api/v1/settings/
```

**Respuesta:**
```json
{
  "vip_monthly_price": "39900.00",           // Precio mensual en COP
  "loyalty_months_required": 3,               // Meses para recompensa
  "loyalty_voucher_service": {
    "id": 5,
    "name": "Masaje Relajante 60min",
    "category": "Masajes"
  },
  "credit_expiration_days": 365
}
```

---

### 2.3 Servicio con Precio VIP

```typescript
interface Service {
  id: number;
  name: string;
  description: string;
  category: {
    id: number;
    name: string;
  };
  duration: number;                    // Minutos
  price: string;                       // Precio regular (ej: "80000.00")
  vip_price: string | null;            // Precio VIP (ej: "60000.00")
  is_active: boolean;
  image: string | null;
}
```

**Endpoint:**
```
GET /api/v1/services/
```

---

### 2.4 Pago de Suscripción VIP

```typescript
interface Payment {
  id: number;
  user: number;
  amount: string;                      // Decimal como string
  status: 'PENDING' | 'APPROVED' | 'DECLINED' | 'ERROR' | 'TIMEOUT';
  payment_type: 'VIP_SUBSCRIPTION' | 'APPOINTMENT' | 'VOUCHER' | 'CREDIT_LOAD';
  transaction_id: string;              // Referencia Wompi
  payment_method: string | null;       // "CARD", "NEQUI", etc.
  created_at: string;                  // ISO timestamp
  updated_at: string;
}
```

**Endpoint:**
```
GET /api/v1/finances/payments/my/
```

---

### 2.5 Log de Suscripción

```typescript
interface SubscriptionLog {
  id: number;
  user: number;
  payment: number;                     // ID del pago
  start_date: string;                  // YYYY-MM-DD
  end_date: string;                    // YYYY-MM-DD
  created_at: string;
}
```

---

## 3. API Endpoints

### 3.1 Iniciar Suscripción VIP

**Endpoint:**
```
POST /api/v1/finances/payments/vip-subscription/initiate/
```

**Permisos:** `IsAuthenticated`, `IsVerified`

**Request Body:** (vacío)

**Response (200 OK):**
```json
{
  "publicKey": "pub_test_xxxxx",
  "amountInCents": 3990000,                    // 39900 COP * 100
  "reference": "vip_sub_123_1639430400",
  "signatureIntegrity": "hash_signature",
  "redirectUrl": "http://localhost:3000/vip/payment-result",
  "currency": "COP"
}
```

**Errores:**
- `400 Bad Request`: Usuario ya es VIP o no verificado
- `401 Unauthorized`: No autenticado
- `500 Internal Server Error`: Error generando pago

**Uso:** Estos datos se pasan al widget de Wompi para iniciar el pago.

---

### 3.2 Cancelar Auto-Renovación

**Endpoint:**
```
POST /api/v1/spa/vip/cancel-subscription/
```

**Permisos:** `IsAuthenticated`, `IsVerified`

**Request Body:** (vacío)

**Response (200 OK):**
```json
{
  "message": "Auto-renovación de suscripción VIP cancelada exitosamente.",
  "vip_auto_renew": false
}
```

**Errores:**
- `400 Bad Request`: No tiene suscripción activa o ya está cancelada
- `401 Unauthorized`: No autenticado

**Nota:** El usuario seguirá siendo VIP hasta `vip_expires_at`, pero no se renovará automáticamente.

---

### 3.3 Historial de Pagos

**Endpoint:**
```
GET /api/v1/finances/payments/my/
```

**Permisos:** `IsAuthenticated`

**Query Params:**
- `page` (opcional): Número de página
- `page_size` (opcional): Items por página

**Response (200 OK):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 123,
      "amount": "39900.00",
      "status": "APPROVED",
      "payment_type": "VIP_SUBSCRIPTION",
      "transaction_id": "123456-1639430400",
      "payment_method": "CARD",
      "created_at": "2024-12-13T10:00:00Z",
      "updated_at": "2024-12-13T10:01:30Z"
    },
    // ... más pagos
  ]
}
```

---

### 3.4 Webhook de Wompi (Backend only)

**Endpoint:**
```
POST /api/v1/finances/webhooks/wompi/
```

**Permisos:** `AllowAny` (con verificación de firma)

**Nota:** Este endpoint es llamado automáticamente por Wompi después de un pago. **No debe ser llamado desde el frontend.**

---

### 3.5 Obtener Datos del Usuario Actual

**Endpoint:**
```
GET /api/v1/users/me/
```

**Permisos:** `IsAuthenticated`

**Response (200 OK):**
```json
{
  "id": 123,
  "phone_number": "+573001234567",
  "email": "user@example.com",
  "first_name": "Juan",
  "last_name": "Pérez",
  "role": "VIP",
  "vip_expires_at": "2025-01-13",
  "vip_active_since": "2024-10-13",
  "vip_auto_renew": true,
  "vip_failed_payments": 0,
  "is_vip": true,
  "created_at": "2024-01-15T08:00:00Z"
}
```

---

## 4. Flujos de Usuario

### 4.1 Flujo: Hacerse VIP (Primera Vez)

```
1. Usuario ve página de "Hazte VIP" con beneficios
2. Click en "Suscribirse por $50,000/mes"
3. Frontend llama: POST /api/v1/finances/payments/vip-subscription/initiate/
4. Backend retorna datos de Wompi
5. Frontend abre widget de Wompi con los datos
6. Usuario completa pago en Wompi
7. Wompi redirige a: /vip/payment-result?id=TRANSACTION_ID
8. Wompi notifica al backend vía webhook
9. Backend:
   - Actualiza payment.status = APPROVED
   - Cambia user.role = VIP
   - Establece user.vip_expires_at = hoy + 30 días
   - Establece user.vip_active_since = hoy
   - Establece user.vip_auto_renew = true
   - Guarda user.vip_payment_token (encriptado)
   - Crea SubscriptionLog
10. Frontend muestra página de éxito
11. Usuario ahora ve precios VIP en servicios
```

**Diagrama:**
```
[Usuario] → [Página VIP] → [Iniciar Pago] → [Widget Wompi]
                                                    ↓
                                              [Pago Exitoso]
                                                    ↓
                                    [Webhook] → [Backend actualiza]
                                                    ↓
                                              [Usuario es VIP]
```

---

### 4.2 Flujo: Renovación Automática Mensual

```
1. Tarea Celery corre diariamente: process_recurring_subscriptions()
2. Busca usuarios con:
   - role = VIP
   - vip_auto_renew = true
   - vip_expires_at en los próximos 3 días
3. Para cada usuario:
   a. Intenta cobrar usando vip_payment_token guardado
   b. Si éxito:
      - Extiende vip_expires_at por 30 días más
      - Resetea vip_failed_payments = 0
      - Crea nuevo Payment y SubscriptionLog
   c. Si falla:
      - Incrementa vip_failed_payments
      - Envía notificación VIP_RENEWAL_FAILED
   d. Si vip_failed_payments >= 3:
      - Establece vip_auto_renew = false
      - Envía notificación de cancelación
4. En vip_expires_at + 1 día, otra tarea downgrade_expired_vips():
   - Cambia role = CLIENT
   - Limpia campos VIP
   - Envía notificación VIP_MEMBERSHIP_EXPIRED
```

---

### 4.3 Flujo: Cancelar Auto-Renovación

```
1. Usuario va a "Mi Membresía VIP"
2. Click en "Cancelar Auto-Renovación"
3. Modal de confirmación: "¿Estás seguro?"
4. Confirma
5. Frontend llama: POST /api/v1/spa/vip/cancel-subscription/
6. Backend:
   - Establece user.vip_auto_renew = false
   - Retorna confirmación
7. Frontend muestra mensaje: "Cancelado. Seguirás siendo VIP hasta [fecha]"
8. Usuario puede volver a activarlo comprando de nuevo
```

---

### 4.4 Flujo: Recompensa de Lealtad

```
1. Tarea Celery corre diariamente: check_vip_loyalty()
2. Busca usuarios VIP con:
   - vip_active_since hace >= loyalty_months_required meses
   - Sin recompensa en el último mes
3. Para cada usuario:
   a. Crea Voucher para loyalty_voucher_service
   b. Crea LoyaltyRewardLog
   c. Envía notificación LOYALTY_REWARD_ISSUED
4. Usuario recibe notificación en app
5. Usuario puede usar voucher en próxima cita
```

---

## 5. Componentes Sugeridos

### 5.1 Página: `/vip` - Información y Suscripción

**Componentes:**
- `VIPHeroSection` - Banner principal con CTA
- `VIPBenefitsList` - Lista de beneficios (precios especiales, recompensas)
- `VIPPricingCard` - Card con precio mensual
- `VIPFAQSection` - Preguntas frecuentes
- `VIPTestimonials` - Testimonios de clientes VIP

**Estado necesario:**
```typescript
interface VIPPageState {
  user: User | null;
  vipPrice: string;            // De GlobalSettings
  loyaltyMonths: number;       // De GlobalSettings
  loyaltyService: Service;     // De GlobalSettings
  isLoading: boolean;
}
```

**Acciones:**
```typescript
async function handleSubscribe() {
  // 1. Verificar autenticación
  if (!user) {
    router.push('/login?redirect=/vip');
    return;
  }

  // 2. Verificar si ya es VIP
  if (user.is_vip) {
    toast.error('Ya eres miembro VIP');
    return;
  }

  // 3. Iniciar pago
  setLoading(true);
  try {
    const response = await fetch('/api/v1/finances/payments/vip-subscription/initiate/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error('Error iniciando pago');
    }

    const wompiData = await response.json();

    // 4. Abrir widget de Wompi
    openWompiWidget(wompiData);
  } catch (error) {
    toast.error('Error al iniciar suscripción');
  } finally {
    setLoading(false);
  }
}
```

---

### 5.2 Página: `/vip/membership` - Panel de Membresía

**Solo visible para usuarios VIP**

**Componentes:**
- `MembershipStatusCard` - Estado actual (expira, activa desde)
- `MembershipBenefitsUsed` - Estadísticas de uso
- `AutoRenewalToggle` - Activar/desactivar auto-renovación
- `PaymentHistoryTable` - Historial de pagos
- `LoyaltyProgressBar` - Progreso hacia próxima recompensa

**Estado necesario:**
```typescript
interface MembershipState {
  user: User;
  payments: Payment[];
  nextRewardDate: Date | null;
  monthsUntilReward: number;
  isLoadingPayments: boolean;
}
```

**Cálculo de progreso de lealtad:**
```typescript
function calculateLoyaltyProgress(user: User, loyaltyMonthsRequired: number) {
  if (!user.vip_active_since) return { months: 0, percentage: 0 };

  const activeDate = new Date(user.vip_active_since);
  const today = new Date();

  const monthsDiff = (today.getFullYear() - activeDate.getFullYear()) * 12
                   + (today.getMonth() - activeDate.getMonth());

  const monthsInCurrentCycle = monthsDiff % loyaltyMonthsRequired;
  const percentage = (monthsInCurrentCycle / loyaltyMonthsRequired) * 100;

  return {
    months: monthsInCurrentCycle,
    percentage,
    nextRewardIn: loyaltyMonthsRequired - monthsInCurrentCycle,
  };
}
```

---

### 5.3 Componente: `VIPBadge`

**Mostrar badge VIP junto al nombre del usuario**

```tsx
interface VIPBadgeProps {
  user: User;
  size?: 'sm' | 'md' | 'lg';
}

function VIPBadge({ user, size = 'md' }: VIPBadgeProps) {
  if (!user.is_vip) return null;

  return (
    <span className={`vip-badge vip-badge-${size}`}>
      <CrownIcon />
      <span>VIP</span>
    </span>
  );
}
```

---

### 5.4 Componente: `ServiceCard` con Precio VIP

```tsx
interface ServiceCardProps {
  service: Service;
  user: User | null;
}

function ServiceCard({ service, user }: ServiceCardProps) {
  const isVip = user?.is_vip || false;
  const hasVipPrice = service.vip_price !== null;

  const displayPrice = isVip && hasVipPrice
    ? service.vip_price
    : service.price;

  const savings = hasVipPrice && isVip
    ? parseFloat(service.price) - parseFloat(service.vip_price!)
    : 0;

  return (
    <div className="service-card">
      <img src={service.image} alt={service.name} />
      <h3>{service.name}</h3>
      <p>{service.description}</p>

      <div className="price-section">
        {isVip && hasVipPrice ? (
          <>
            <span className="original-price">${formatPrice(service.price)}</span>
            <span className="vip-price">${formatPrice(displayPrice)}</span>
            <span className="savings">Ahorras ${formatPrice(savings)}</span>
          </>
        ) : (
          <span className="price">${formatPrice(displayPrice)}</span>
        )}

        {!isVip && hasVipPrice && (
          <div className="vip-promotion">
            <p>Precio VIP: ${formatPrice(service.vip_price!)}</p>
            <a href="/vip">Hazte VIP</a>
          </div>
        )}
      </div>

      <button>Reservar</button>
    </div>
  );
}
```

---

### 5.5 Componente: `AutoRenewalControl`

```tsx
interface AutoRenewalControlProps {
  user: User;
  onUpdate: (user: User) => void;
}

function AutoRenewalControl({ user, onUpdate }: AutoRenewalControlProps) {
  const [isLoading, setIsLoading] = useState(false);

  async function handleToggle() {
    if (!user.vip_auto_renew) {
      // Para reactivar, necesitan comprar de nuevo
      toast.info('Para reactivar, realiza una nueva compra VIP');
      return;
    }

    // Cancelar auto-renovación
    const confirmed = await confirm(
      '¿Cancelar auto-renovación?',
      'Seguirás siendo VIP hasta ' + formatDate(user.vip_expires_at!)
    );

    if (!confirmed) return;

    setIsLoading(true);
    try {
      const response = await fetch('/api/v1/spa/vip/cancel-subscription/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) throw new Error('Error cancelando');

      const data = await response.json();

      // Actualizar usuario localmente
      const updatedUser = { ...user, vip_auto_renew: false };
      onUpdate(updatedUser);

      toast.success('Auto-renovación cancelada');
    } catch (error) {
      toast.error('Error al cancelar');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="auto-renewal-control">
      <div className="info">
        <h4>Auto-Renovación</h4>
        <p>
          {user.vip_auto_renew
            ? 'Tu membresía se renovará automáticamente cada mes'
            : 'Auto-renovación desactivada. Expira el ' + formatDate(user.vip_expires_at!)
          }
        </p>
      </div>

      <Switch
        checked={user.vip_auto_renew}
        onChange={handleToggle}
        disabled={isLoading}
      />
    </div>
  );
}
```

---

## 6. Integración de Pagos (Wompi)

### 6.1 Configuración del Widget

**Script a incluir en el HTML:**
```html
<script src="https://checkout.wompi.co/widget.js"></script>
```

**Función para abrir widget:**
```typescript
interface WompiCheckoutData {
  publicKey: string;
  amountInCents: number;
  reference: string;
  signatureIntegrity: string;
  redirectUrl: string;
  currency: string;
}

function openWompiWidget(data: WompiCheckoutData) {
  const checkout = new WidgetCheckout({
    currency: data.currency,
    amountInCents: data.amountInCents,
    reference: data.reference,
    publicKey: data.publicKey,
    redirectUrl: data.redirectUrl,
    signature: {
      integrity: data.signatureIntegrity,
    },
  });

  checkout.open((result) => {
    const transaction = result.transaction;
    console.log('Transaction result:', transaction);

    // El redirect se maneja automáticamente
    // No es necesario hacer nada aquí
  });
}
```

---

### 6.2 Página de Resultado: `/vip/payment-result`

**Query params recibidos:**
- `id`: Transaction ID de Wompi

**Flujo:**
```typescript
function VIPPaymentResultPage() {
  const searchParams = useSearchParams();
  const transactionId = searchParams.get('id');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');

  useEffect(() => {
    async function checkPayment() {
      if (!transactionId) {
        setStatus('error');
        return;
      }

      // Esperar a que el webhook procese (puede tardar unos segundos)
      await new Promise(resolve => setTimeout(resolve, 3000));

      try {
        // Verificar el estado del pago
        const response = await fetch('/api/v1/finances/payments/my/');
        const data = await response.json();

        const payment = data.results.find(
          (p: Payment) => p.transaction_id === transactionId
        );

        if (payment?.status === 'APPROVED') {
          setStatus('success');

          // Recargar datos del usuario
          await refreshUserData();
        } else {
          setStatus('error');
        }
      } catch (error) {
        setStatus('error');
      }
    }

    checkPayment();
  }, [transactionId]);

  if (status === 'loading') {
    return <LoadingSpinner message="Verificando pago..." />;
  }

  if (status === 'success') {
    return (
      <div className="payment-success">
        <CheckIcon />
        <h1>¡Bienvenido a VIP!</h1>
        <p>Tu suscripción ha sido activada exitosamente</p>
        <p>Ahora disfrutas de precios especiales en todos nuestros servicios</p>
        <button onClick={() => router.push('/vip/membership')}>
          Ver mi membresía
        </button>
      </div>
    );
  }

  return (
    <div className="payment-error">
      <ErrorIcon />
      <h1>Error en el pago</h1>
      <p>No pudimos procesar tu suscripción</p>
      <button onClick={() => router.push('/vip')}>
        Intentar de nuevo
      </button>
    </div>
  );
}
```

---

## 7. Estados y Permisos

### 7.1 Estados Posibles de Usuario

| Estado | role | vip_expires_at | vip_auto_renew | is_vip | Descripción |
|--------|------|----------------|----------------|--------|-------------|
| Cliente Normal | CLIENT | null | false | false | Usuario regular |
| VIP Activo | VIP | futuro | true | true | VIP con renovación activa |
| VIP Sin Renovación | VIP | futuro | false | true | VIP que canceló pero aún válido |
| VIP Expirado | CLIENT | pasado | false | false | Ex-VIP que expiró |

### 7.2 Validaciones en Frontend

```typescript
// Verificar si puede comprar VIP
function canPurchaseVIP(user: User | null): boolean {
  if (!user) return false;
  if (user.role === 'VIP' && user.is_vip) return false;
  return true;
}

// Verificar si puede cancelar auto-renovación
function canCancelAutoRenew(user: User | null): boolean {
  if (!user || !user.is_vip) return false;
  return user.vip_auto_renew === true;
}

// Calcular días restantes de VIP
function daysUntilExpiration(user: User): number {
  if (!user.vip_expires_at) return Infinity;

  const expiryDate = new Date(user.vip_expires_at);
  const today = new Date();
  const diffTime = expiryDate.getTime() - today.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  return diffDays;
}

// Advertencia de próxima expiración
function shouldShowExpirationWarning(user: User): boolean {
  if (!user.is_vip || user.vip_auto_renew) return false;

  const daysLeft = daysUntilExpiration(user);
  return daysLeft <= 7 && daysLeft > 0;
}
```

---

## 8. Notificaciones

### 8.1 Eventos de Notificación VIP

El backend envía notificaciones push en estos casos:

| Evento | Código | Cuándo |
|--------|--------|--------|
| Renovación fallida | `VIP_RENEWAL_FAILED` | Cada vez que falla el cobro automático |
| Membresía expirada | `VIP_MEMBERSHIP_EXPIRED` | Cuando expira y se convierte en CLIENT |
| Recompensa de lealtad | `LOYALTY_REWARD_ISSUED` | Cuando recibe voucher por lealtad |

### 8.2 Endpoint de Notificaciones

```
GET /api/v1/notifications/
```

**Response:**
```json
{
  "count": 3,
  "results": [
    {
      "id": 456,
      "event": "LOYALTY_REWARD_ISSUED",
      "message": "¡Felicidades! Has recibido un voucher de Masaje Relajante por tu lealtad VIP",
      "data": {
        "voucher_id": 789,
        "service_name": "Masaje Relajante 60min"
      },
      "is_read": false,
      "created_at": "2024-12-13T10:00:00Z"
    }
  ]
}
```

### 8.3 Componente de Notificación

```tsx
function VIPNotificationBanner({ user }: { user: User }) {
  if (!user.is_vip) return null;

  const daysLeft = daysUntilExpiration(user);
  const showWarning = shouldShowExpirationWarning(user);

  if (user.vip_failed_payments > 0) {
    return (
      <div className="notification warning">
        <AlertIcon />
        <p>
          El último cobro automático falló.
          Intentos restantes: {3 - user.vip_failed_payments}
        </p>
        <button onClick={() => router.push('/vip/membership')}>
          Actualizar método de pago
        </button>
      </div>
    );
  }

  if (showWarning) {
    return (
      <div className="notification info">
        <InfoIcon />
        <p>
          Tu membresía VIP expira en {daysLeft} días.
        </p>
        <button onClick={() => router.push('/vip')}>
          Renovar ahora
        </button>
      </div>
    );
  }

  return null;
}
```

---

## 9. Ejemplos de Código

### 9.1 Hook: `useVIPStatus`

```typescript
interface VIPStatus {
  isVip: boolean;
  expiresAt: Date | null;
  daysLeft: number;
  autoRenew: boolean;
  failedPayments: number;
  canPurchase: boolean;
  canCancel: boolean;
  loyaltyProgress: {
    months: number;
    percentage: number;
    nextRewardIn: number;
  };
}

function useVIPStatus(): VIPStatus | null {
  const { user } = useAuth();
  const { data: settings } = useSWR('/api/v1/settings/');

  if (!user || !settings) return null;

  const expiresAt = user.vip_expires_at
    ? new Date(user.vip_expires_at)
    : null;

  const daysLeft = expiresAt
    ? Math.ceil((expiresAt.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : 0;

  const loyaltyProgress = calculateLoyaltyProgress(
    user,
    settings.loyalty_months_required
  );

  return {
    isVip: user.is_vip,
    expiresAt,
    daysLeft,
    autoRenew: user.vip_auto_renew,
    failedPayments: user.vip_failed_payments,
    canPurchase: canPurchaseVIP(user),
    canCancel: canCancelAutoRenew(user),
    loyaltyProgress,
  };
}
```

---

### 9.2 Servicio: `vipService.ts`

```typescript
const vipService = {
  async initiateSubscription(): Promise<WompiCheckoutData> {
    const response = await apiClient.post(
      '/api/v1/finances/payments/vip-subscription/initiate/'
    );
    return response.data;
  },

  async cancelAutoRenewal(): Promise<void> {
    await apiClient.post('/api/v1/spa/vip/cancel-subscription/');
  },

  async getPaymentHistory(page = 1): Promise<PaginatedResponse<Payment>> {
    const response = await apiClient.get(
      `/api/v1/finances/payments/my/?page=${page}`
    );
    return response.data;
  },

  async getVIPPrice(): Promise<string> {
    const response = await apiClient.get('/api/v1/settings/');
    return response.data.vip_monthly_price;
  },
};
```

---

### 9.3 Página Completa: VIP Landing

```tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { vipService } from '@/services/vipService';

export default function VIPPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [vipPrice, setVipPrice] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    async function loadVIPPrice() {
      const price = await vipService.getVIPPrice();
      setVipPrice(price);
    }
    loadVIPPrice();
  }, []);

  async function handleSubscribe() {
    if (!user) {
      router.push('/login?redirect=/vip');
      return;
    }

    if (user.is_vip) {
      router.push('/vip/membership');
      return;
    }

    setIsLoading(true);
    try {
      const wompiData = await vipService.initiateSubscription();
      openWompiWidget(wompiData);
    } catch (error) {
      console.error('Error:', error);
      alert('Error al iniciar suscripción');
    } finally {
      setIsLoading(false);
    }
  }

  if (authLoading) {
    return <div>Cargando...</div>;
  }

  return (
    <div className="vip-page">
      {/* Hero Section */}
      <section className="hero">
        <h1>Hazte Miembro VIP</h1>
        <p>Accede a precios exclusivos y beneficios premium</p>

        {user?.is_vip ? (
          <button onClick={() => router.push('/vip/membership')}>
            Ver mi membresía
          </button>
        ) : (
          <button
            onClick={handleSubscribe}
            disabled={isLoading}
          >
            {isLoading ? 'Procesando...' : `Suscribirse por $${formatPrice(vipPrice)}/mes`}
          </button>
        )}
      </section>

      {/* Benefits */}
      <section className="benefits">
        <h2>Beneficios Exclusivos</h2>

        <div className="benefit-grid">
          <div className="benefit-card">
            <PriceTagIcon />
            <h3>Precios Especiales</h3>
            <p>Hasta 25% de descuento en todos nuestros servicios</p>
          </div>

          <div className="benefit-card">
            <GiftIcon />
            <h3>Recompensas de Lealtad</h3>
            <p>Servicio gratuito cada 3 meses de membresía continua</p>
          </div>

          <div className="benefit-card">
            <CalendarIcon />
            <h3>Prioridad en Reservas</h3>
            <p>Acceso preferencial a horarios y fechas</p>
          </div>

          <div className="benefit-card">
            <CrownIcon />
            <h3>Status Premium</h3>
            <p>Reconocimiento especial como cliente VIP</p>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="pricing">
        <div className="pricing-card">
          <h3>Membresía VIP</h3>
          <div className="price">
            <span className="currency">$</span>
            <span className="amount">{formatPrice(vipPrice)}</span>
            <span className="period">/mes</span>
          </div>

          <ul className="features">
            <li>✓ Precios VIP en todos los servicios</li>
            <li>✓ Renovación automática mensual</li>
            <li>✓ Servicio gratuito cada 3 meses</li>
            <li>✓ Cancela cuando quieras</li>
          </ul>

          <button
            onClick={handleSubscribe}
            disabled={isLoading || user?.is_vip}
          >
            {user?.is_vip ? 'Ya eres VIP' : 'Suscribirse ahora'}
          </button>
        </div>
      </section>

      {/* FAQ */}
      <section className="faq">
        <h2>Preguntas Frecuentes</h2>

        <details>
          <summary>¿Cómo funciona la renovación automática?</summary>
          <p>
            Tu membresía se renueva automáticamente cada mes usando el método
            de pago que registraste. Puedes cancelar en cualquier momento y
            seguirás teniendo acceso VIP hasta el final del periodo pagado.
          </p>
        </details>

        <details>
          <summary>¿Qué pasa si cancelo?</summary>
          <p>
            Puedes cancelar la renovación automática cuando quieras. Seguirás
            disfrutando de los beneficios VIP hasta la fecha de expiración.
            Para reactivar, simplemente vuelve a suscribirte.
          </p>
        </details>

        <details>
          <summary>¿Cómo funcionan las recompensas de lealtad?</summary>
          <p>
            Después de 3 meses consecutivos como VIP, recibirás automáticamente
            un voucher para un servicio gratuito. Este beneficio se repite cada
            3 meses mientras mantengas tu membresía activa.
          </p>
        </details>
      </section>
    </div>
  );
}
```

---

## 10. Checklist de Implementación

### Frontend

- [ ] Página `/vip` - Landing con información y suscripción
- [ ] Página `/vip/membership` - Panel de membresía (solo VIP)
- [ ] Página `/vip/payment-result` - Resultado de pago
- [ ] Componente `VIPBadge` - Badge visual para usuarios VIP
- [ ] Componente `ServiceCard` - Mostrar precios VIP vs regulares
- [ ] Componente `AutoRenewalControl` - Toggle de auto-renovación
- [ ] Componente `PaymentHistoryTable` - Historial de pagos
- [ ] Componente `LoyaltyProgressBar` - Progreso hacia recompensa
- [ ] Hook `useVIPStatus` - Estado VIP del usuario
- [ ] Servicio `vipService` - Llamadas a API
- [ ] Integración widget Wompi
- [ ] Notificaciones push para eventos VIP
- [ ] Validaciones de permisos (rutas protegidas)

### Testing

- [ ] Flujo completo: Compra VIP
- [ ] Flujo completo: Cancelar auto-renovación
- [ ] Mostrar precios VIP correctamente en servicios
- [ ] Redirección después de pago exitoso/fallido
- [ ] Notificaciones de expiración
- [ ] Cálculo de progreso de lealtad
- [ ] Historial de pagos paginado

---

## 11. Variables de Entorno Necesarias

**Frontend `.env.local`:**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WOMPI_REDIRECT_URL=http://localhost:3000/vip/payment-result
```

**Backend ya tiene:**
```bash
WOMPI_PUBLIC_KEY=pub_test_xxxxx
WOMPI_PRIVATE_KEY=prv_test_xxxxx
WOMPI_INTEGRITY_SECRET=xxxxx
WOMPI_EVENT_SECRET=xxxxx
```

---

## 12. Notas Importantes

### 🔐 Seguridad

1. **Tokens encriptados**: Los tokens de pago se guardan encriptados con Fernet
2. **Validación de webhook**: Wompi webhook requiere firma de seguridad
3. **Permisos**: Todas las operaciones VIP requieren autenticación

### 💳 Pagos

1. **Sandbox vs Producción**: Usar claves correctas según ambiente
2. **Timeout**: Widget tiene timeout de 10 minutos
3. **Webhook delay**: Puede tardar 3-5 segundos en procesar

### 📊 Datos

1. **Precios**: Siempre como strings decimales ("39900.00")
2. **Fechas**: ISO 8601 format (YYYY-MM-DD)
3. **Montos Wompi**: En centavos (39900 COP = 3990000 centavos)

---

## 13. Recursos Adicionales

### Documentación Wompi
- [Widget de Checkout](https://docs.wompi.co/docs/widget-checkout)
- [Webhooks](https://docs.wompi.co/docs/eventos-webhook)
- [Tokenización](https://docs.wompi.co/docs/recaudos-recurrentes)

### Archivos Backend de Referencia
- `users/models.py` - Modelo CustomUser con campos VIP
- `finances/views.py` - Vistas de pagos y webhooks
- `finances/subscriptions.py` - Lógica de suscripciones
- `spa/views/packages.py` - Cancelación de auto-renovación
- `finances/tasks.py` - Tareas periódicas (renovación, expiración)

---

**Fecha de documentación:** 13 de Diciembre, 2024
**Versión Backend:** 1.0
**Estado:** ✅ Sistema VIP completamente implementado y funcional
