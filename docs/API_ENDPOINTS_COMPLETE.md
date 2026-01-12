# 📋 LISTA COMPLETA DE ENDPOINTS - SERVICIOS Y CONFIGURACIÓN

**Base URL Backend:** `http://localhost:8000`

---

## ✅ ENDPOINTS VERIFICADOS Y FUNCIONALES

### 🔧 **SERVICIOS (SPA)**

#### 1. Listar Servicios
```
GET /api/v1/spa/services/
```
**Autenticación:** Requerida  
**Permisos:** Usuarios autenticados  
**Query Params:**
- `category={uuid}` - Filtrar por categoría
- `is_active=true|false` - Filtrar activos/inactivos
- `search={texto}` - Buscar en nombre/descripción
- `ordering=name|-price|duration` - Ordenar
- `page=1&page_size=20` - Paginación

**Response Example:**
```json
{
  "count": 10,
  "next": "http://localhost:8000/api/v1/spa/services/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid-here",
      "name": "Masaje Relajante",
      "description": "Masaje de cuerpo completo con aceites esenciales",
      "duration": 60,
      "price": "80000.00",
      "vip_price": "68000.00",
      "category": "uuid-category",
      "category_name": "Masajes",
      "is_active": true
    }
  ]
}
```

#### 2. Obtener Servicio por ID
```
GET /api/v1/spa/services/{id}/
```

#### 3. Crear Servicio (ADMIN)
```
POST /api/v1/spa/services/
Content-Type: application/json
Authorization: Bearer {token}

{
  "name": "Masaje Terapéutico",
  "description": "Descripción del servicio",
  "duration": 90,
  "price": "120000.00",
  "vip_price": "102000.00",
  "category": "uuid-category",
  "is_active": true
}
```

#### 4. Actualizar Servicio (ADMIN)
```
PATCH /api/v1/spa/services/{id}/
PUT /api/v1/spa/services/{id}/
```

#### 5. Eliminar Servicio (ADMIN - Soft Delete)
```
DELETE /api/v1/spa/services/{id}/
```

#### 6. Toggle Activo/Inactivo (ADMIN)
```
POST /api/v1/spa/services/{id}/toggle_active/
```

#### 7. Solo Servicios Activos
```
GET /api/v1/spa/services/active/
```

---

### 📁 **CATEGORÍAS DE SERVICIOS**

#### 1. Listar Categorías
```
GET /api/v1/spa/service-categories/
```
**Response:**
```json
{
  "count": 5,
  "results": [
    {
      "id": "uuid",
      "name": "Masajes",
      "description": "Servicios de masajes terapéuticos",
      "is_low_supervision": false
    }
  ]
}
```

#### 2. Crear Categoría (ADMIN)
```
POST /api/v1/spa/service-categories/

{
  "name": "Faciales",
  "description": "Tratamientos faciales",
  "is_low_supervision": true
}
```

#### 3. Actualizar/Eliminar Categoría (ADMIN)
```
PATCH /api/v1/spa/service-categories/{id}/
DELETE /api/v1/spa/service-categories/{id}/
```

---

### 🚫 **EXCLUSIONES DE DISPONIBILIDAD**

#### 1. Listar Exclusiones
```
GET /api/v1/spa/availability-exclusions/
```

#### 2. Crear Exclusión (ADMIN)
```
POST /api/v1/spa/availability-exclusions/

{
  "staff_member": "uuid",
  "date": "2025-12-25",
  "start_time": "00:00",
  "end_time": "23:59",
  "reason": "Navidad"
}
```

#### 3. Exclusiones Futuras
```
GET /api/v1/spa/availability-exclusions/upcoming/
```

#### 4. Crear Múltiples (ADMIN)
```
POST /api/v1/spa/availability-exclusions/bulk_create/

{
  "exclusions": [...]
}
```

---

### ⚙️ **CONFIGURACIÓN GLOBAL**

#### 1. Obtener Configuración
```
GET /api/v1/core/settings/
```

#### 2. Actualizar Configuración (ADMIN)
```
PATCH /api/v1/core/settings/1/
```

---

### 🤖 **CONFIGURACIÓN DEL BOT**

#### 1. Obtener Config Bot
```
GET /api/v1/bot/config/
```

#### 2. Actualizar Config Bot (ADMIN)
```
PATCH /api/v1/bot/config/{id}/
```

---

### 📄 **PÁGINA QUIÉNES SOMOS**

#### 1. Obtener Página About
```
GET /api/v1/core/about/
```

#### 2. Actualizar About (ADMIN)
```
PATCH /api/v1/core/about/1/
```

#### 3. Miembros del Equipo
```
GET /api/v1/core/team-members/
POST /api/v1/core/team-members/ (ADMIN)
```

#### 4. Galería de Imágenes
```
GET /api/v1/core/gallery-images/
POST /api/v1/core/gallery-images/ (ADMIN)
```

---

### 📝 **BLOG**

#### 1. Listar Artículos
```
GET /api/v1/blog/articles/
```

#### 2. Artículos Destacados
```
GET /api/v1/blog/articles/featured/
```

#### 3. Crear/Editar Artículo (ADMIN)
```
POST /api/v1/blog/articles/
PATCH /api/v1/blog/articles/{slug}/
```

#### 4. Publicar/Despublicar (ADMIN)
```
POST /api/v1/blog/articles/{slug}/publish/
POST /api/v1/blog/articles/{slug}/unpublish/
```

---

### 🛒 **PRODUCTOS (MARKETPLACE)**

#### 1. Listar Productos (ADMIN)
```
GET /api/v1/marketplace/admin/products/
```

#### 2. Crear Producto (ADMIN)
```
POST /api/v1/marketplace/admin/products/
```

#### 3. Variantes de Producto (ADMIN)
```
GET /api/v1/marketplace/admin/variants/
POST /api/v1/marketplace/admin/variants/
```

---

## 🔑 **AUTENTICACIÓN**

Todos los endpoints requieren JWT Token:

```javascript
headers: {
  'Authorization': 'Bearer {access_token}',
  'Content-Type': 'application/json'
}
```

---

## ⚠️ **PERMISOS**

- **Lectura (GET)**: Usuarios autenticados
- **Escritura (POST/PUT/PATCH/DELETE)**: Solo ADMIN (role='ADMIN')

---

## 💡 **EJEMPLO DE USO EN REACT/NEXT.JS**

```typescript
// lib/axios.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para agregar token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default apiClient;
```

```typescript
// hooks/useServices.ts
import { useState, useEffect } from 'react';
import apiClient from '@/lib/axios';

export const useServices = () => {
  const [services, setServices] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchServices = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/spa/services/', {
        params: { is_active: true }
      });
      setServices(response.data.results || response.data);
    } catch (error) {
      console.error('Error fetching services:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await apiClient.get('/spa/service-categories/');
      setCategories(response.data.results || response.data);
    } catch (error) {
      console.error('Error fetching categories:', error);
    }
  };

  useEffect(() => {
    fetchServices();
    fetchCategories();
  }, []);

  return { services, categories, loading, fetchServices, fetchCategories };
};
```

---

## 🔄 **TROUBLESHOOTING**

### Error 404 en endpoints
1. Verificar que el servidor esté corriendo: `docker compose ps`
2. Reiniciar el servidor: `docker compose restart web`
3. Ver logs: `docker compose logs web --tail=100`

### Error 401 Unauthorized
- Verificar que el token JWT esté en localStorage
- Verificar que el token no haya expirado (15 min)
- Usar el refresh token para obtener uno nuevo

### Error 403 Forbidden
- Verificar que el usuario tenga rol ADMIN para endpoints de escritura
- Verificar permisos en el backend

---

## 📊 **RESUMEN DE ENDPOINTS IMPLEMENTADOS**

| Módulo | Endpoints | Estado |
|--------|-----------|--------|
| Servicios | 7 | ✅ Activo |
| Categorías | 5 | ✅ Activo |
| Exclusiones | 4 | ✅ Activo |
| Config Global | 3 | ✅ Activo |
| Config Bot | 3 | ✅ Activo |
| About Page | 6 | ✅ Activo |
| Blog | 8 | ✅ Activo |
| Productos | 6 | ✅ Activo |

**Total: 42 endpoints implementados**
