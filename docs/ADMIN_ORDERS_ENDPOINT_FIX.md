# Fix: Error 404 en Admin Orders Endpoint

## 🔍 Diagnóstico del Error

**Error recibido:**
```
AxiosError: Request failed with status code 404
GET /api/v1/marketplace/admin/orders/
```

## ✅ Verificación de URLs

Las URLs están correctamente registradas en el backend:

1. **marketplace/urls.py:36** - Router registrado: `router.register(r'admin/orders', AdminOrderViewSet, basename='admin-order')`
2. **studiozens/urls.py:11** - Marketplace incluido: `path('marketplace/', include('marketplace.urls'))`
3. **studiozens/urls.py:29** - API v1 patterns incluidos

**URL completa esperada:**
```
http://localhost:8000/api/v1/marketplace/admin/orders/
```

## 🎯 Posibles Causas del Error 404

### 1. **El servidor no está corriendo** ⚠️
```bash
# Verificar si el servidor está activo
curl http://localhost:8000/health/
```

### 2. **La URL en el frontend es incorrecta** ⚠️

**CORRECTO:**
```typescript
const response = await apiClient.get<Order[]>(
  `/api/v1/marketplace/admin/orders/?${params.toString()}`
);
```

**INCORRECTO (posibles errores):**
```typescript
// ❌ Falta el prefijo /api/v1/
`/marketplace/admin/orders/`

// ❌ Falta /marketplace/
`/api/v1/admin/orders/`

// ❌ Slash extra al final
`/api/v1/marketplace/admin/orders//?${params}`
```

### 3. **Problema con el apiClient baseURL** ⚠️

Si tu `apiClient` ya tiene configurado un `baseURL`, podría estar duplicando rutas.

**Verifica tu configuración de axios:**
```typescript
// Si tienes esto en tu apiClient:
const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1', // ✅ Con baseURL
});

// Entonces la llamada debería ser:
const response = await apiClient.get<Order[]>(
  `/marketplace/admin/orders/?${params.toString()}`
);
// NO: /api/v1/marketplace/admin/orders/
```

### 4. **Permisos de usuario** ⚠️

El endpoint requiere permisos de ADMIN. Verifica que el token tenga permisos correctos:

```python
# En marketplace/views.py:664
permission_classes = [DomainIsAdminUser]
```

**Para verificar:**
```bash
# Decodifica el JWT token
# Verifica que el usuario tenga role='ADMIN' o is_staff=True
```

### 5. **CORS o proxy inverso** ⚠️

Si estás usando un proxy en Next.js, verifica la configuración:

```javascript
// next.config.js
module.exports = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};
```

## 🔧 Soluciones

### Solución 1: Verificar la URL completa

```typescript
// hooks/useAdminOrders.ts

const fetchOrders = async (filters: OrderFilters) => {
  try {
    const params = new URLSearchParams();

    if (filters.status) {
      params.append('status', filters.status);
    }

    // ✅ OPCIÓN A: Si apiClient NO tiene baseURL
    const response = await apiClient.get<Order[]>(
      `/api/v1/marketplace/admin/orders/?${params.toString()}`
    );

    // ✅ OPCIÓN B: Si apiClient tiene baseURL='/api/v1'
    const response = await apiClient.get<Order[]>(
      `/marketplace/admin/orders/?${params.toString()}`
    );

    return response.data;
  } catch (error) {
    console.error('Error fetching orders:', error);
    throw error;
  }
};
```

### Solución 2: Agregar logging para debugging

```typescript
const fetchOrders = async (filters: OrderFilters) => {
  try {
    const params = new URLSearchParams();

    if (filters.status) {
      params.append('status', filters.status);
    }

    const url = `/api/v1/marketplace/admin/orders/?${params.toString()}`;

    // 🔍 DEBUG: Ver la URL completa
    console.log('Fetching URL:', url);
    console.log('Full URL:', apiClient.defaults.baseURL + url);

    const response = await apiClient.get<Order[]>(url);

    console.log('Response:', response.data);

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      console.error('Axios Error:', {
        url: error.config?.url,
        method: error.config?.method,
        status: error.response?.status,
        data: error.response?.data,
      });
    }
    throw error;
  }
};
```

### Solución 3: Verificar configuración de apiClient

```typescript
// lib/apiClient.ts o similar

import axios from 'axios';

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para agregar token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('adminToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor para logging
apiClient.interceptors.request.use(
  (config) => {
    console.log('🚀 Request:', {
      method: config.method?.toUpperCase(),
      url: config.url,
      baseURL: config.baseURL,
      fullURL: `${config.baseURL}${config.url}`,
    });
    return config;
  },
  (error) => Promise.reject(error)
);
```

### Solución 4: Probar el endpoint manualmente

```bash
# 1. Verificar que el servidor está corriendo
curl http://localhost:8000/health/

# 2. Obtener token de admin
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'

# 3. Probar el endpoint con el token
curl http://localhost:8000/api/v1/marketplace/admin/orders/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# 4. Si funciona, el problema está en el frontend
# 5. Si no funciona, el problema está en el backend
```

### Solución 5: Verificar permisos de CORS

```python
# settings.py

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True

# O para desarrollo:
CORS_ALLOW_ALL_ORIGINS = True  # Solo en desarrollo
```

## 📝 Checklist de Verificación

- [ ] El servidor Django está corriendo en http://localhost:8000
- [ ] La URL en el frontend es exactamente: `/api/v1/marketplace/admin/orders/`
- [ ] El `apiClient` tiene la configuración correcta de `baseURL`
- [ ] El token de autorización se está enviando correctamente
- [ ] El usuario tiene permisos de ADMIN
- [ ] CORS está configurado correctamente
- [ ] No hay slashes duplicados en la URL final
- [ ] El endpoint responde correctamente con curl/Postman

## 🧪 Test Rápido

Crea este archivo temporal para probar:

```typescript
// test-admin-orders.ts

import axios from 'axios';

const testEndpoint = async () => {
  const token = 'TU_TOKEN_AQUI'; // Reemplazar con token real

  try {
    const response = await axios.get(
      'http://localhost:8000/api/v1/marketplace/admin/orders/',
      {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      }
    );

    console.log('✅ SUCCESS:', response.data);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      console.error('❌ ERROR:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        url: error.config?.url,
      });
    }
  }
};

testEndpoint();
```

## 🎯 Respuesta Esperada

Si el endpoint funciona correctamente, deberías recibir:

```json
[
  {
    "id": "uuid-here",
    "user": "user-uuid",
    "status": "PAID",
    "total_amount": "150000.00",
    "shipping_cost": "5000.00",
    "delivery_option": "DELIVERY",
    "delivery_address": "Calle 123...",
    "tracking_number": "",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z",
    "items": [...]
  }
]
```

## 🚨 Errores Comunes

### Error 404
- URL incorrecta
- Servidor no está corriendo
- Ruta no registrada en Django

### Error 401
- Token inválido o expirado
- Token no enviado en headers

### Error 403
- Usuario no tiene permisos de ADMIN
- `DomainIsAdminUser` permission rechaza la petición

### Error 500
- Error en el backend (revisar logs de Django)
- Problema con la base de datos

## 📞 Siguiente Paso

1. Ejecuta el test con curl desde la terminal
2. Si curl funciona, el problema está en el frontend
3. Si curl falla, el problema está en el backend
4. Comparte el resultado para más ayuda
