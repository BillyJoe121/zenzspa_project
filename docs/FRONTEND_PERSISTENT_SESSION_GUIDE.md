# Guía de Implementación: Sesiones Persistentes y Silent Refresh

Esta guía detalla cómo implementar una autenticación robusta y persistente (estilo "Recuérdame siempre") en el Frontend, utilizando los _refresh tokens_ de larga duración configurados en el backend.

## 1. El Concepto: Lógica de Tokens

El backend ahora está configurado para entregar tokens con estas duraciones:
*   **Access Token (Corto):** 15 minutos. Se usa para todas las peticiones API.
*   **Refresh Token (Largo):** 90 días. Se usa **únicamente** para pedir nuevos Access Tokens.

### Comportamiento "Sliding Session" (Rotación)
Cada vez que usas el Refresh Token para renovar la sesión, el backend te devuelve un par nuevo (Nuevo Access + Nuevo Refresh por otros 90 días). Esto significa que **mientras el usuario entre al menos una vez cada 90 días, su sesión nunca expirará**.

---

## 2. Estrategia de Almacenamiento Frontend

Para que la sesión sobreviva al cierre del navegador, debemos usar almacenamiento persistente.

### Opción A (La que usaremos por ahora): `localStorage`
Es la más fácil de implementar y compatible con la estructura JWT actual.
*   **Ventaja:** Fácil acceso desde JS.
*   **Riesgo:** Vulnerable a XSS (si inyectan JS malicioso, pueden robar el token). *Mitigación: Usar buenas prácticas de CSP en el backend.*

### Opción B (Más segura): Cookies `HttpOnly`
Requiere que el backend setee las cookies en la respuesta. Es más robusta pero más compleja de configurar si el frontend y backend están en dominios diferentes (CORS/SameSite). *Podemos migrar a esto a futuro.*

---

## 3. Implementación Paso a Paso (Axios Interceptor)

No queremos que el usuario vea un error 401 ni tenga que loguearse de nuevo. Para esto usamos un **Interceptor de Axios**.

### `src/lib/axios.ts` (O donde configures tu instancia de Axios)

```typescript
import axios from 'axios';

// URL base de tu API
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 1. Interceptor de REQUEST: Inyectar el Access Token si existe
api.interceptors.request.use(
  (config) => {
    // Leemos de localStorage
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Variable para evitar bucles infinitos de refresh
let isRefreshing = false;
let failedQueue: any[] = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// 2. Interceptor de RESPONSE: Manejar errores 401 (Token Expirado)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Si el error es 401 y NO es el intento de refresh en sí mismo
    if (error.response?.status === 401 && !originalRequest._retry) {
      
      // Si ya estamos refrescando, encolamos esta petición para cuando termine
      if (isRefreshing) {
        return new Promise(function (resolve, reject) {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');

        if (!refreshToken) {
          // No hay refresh token, forzamos logout
          throw new Error('No refresh token available');
        }

        // Llamamos al endpoint de refresh
        const response = await axios.post(`${API_URL}/users/token/refresh/`, {
          refresh: refreshToken,
        });

        const { access, refresh } = response.data;

        // Guardamos los tokens NUEVOS (Rotación)
        localStorage.setItem('access_token', access);
        // IMPORTANTE: Si backend tiene ROTATE_REFRESH_TOKENS=True, guardamos el nuevo refresh
        if (refresh) {
            localStorage.setItem('refresh_token', refresh);
        }

        // Actualizamos header por defecto para futuras peticiones
        api.defaults.headers.common.Authorization = `Bearer ${access}`;
        
        // Procesamos la cola de peticiones fallidas
        processQueue(null, access);
        
        // Reintentamos la petición original con el nuevo token
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return api(originalRequest);

      } catch (refreshError) {
        // Si el refresh falla (token expirado > 90 días o inválido)
        processQueue(refreshError, null);
        
        // Limpiamos todo y redirigimos a login
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_data');
        
        // Redirección segura (ajustar según tu router, ej. Next.js router)
        window.location.href = '/login'; 
        
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
```

## 4. Uso en `LoginPage.tsx`

Cuando el usuario hace login exitoso, asegúrate de guardar ambos tokens:

```typescript
const handleLoginSuccess = (response: any) => {
    const { access, refresh, user } = response.data;
    
    // Guardar tokens persistentemente
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
    
    // Guardar datos básicos del usuario
    localStorage.setItem('user_data', JSON.stringify(user));
    
    // Redirigir
    router.push('/dashboard');
};
```

## 5. Verificación de Sesión al Cargar (App.tsx / Layout)

En tu componente raíz o un `AuthProvider`, puedes hacer una verificación rápida al iniciar la app para saber si el usuario está "logueado" (tiene tokens) y restaurar su estado en Redux/Context.

```typescript
useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
        // Opcional: Validar token o simplemente asumir logueado hasta que falle una petición
        store.dispatch(setCredentials({ token, user: JSON.parse(localStorage.getItem('user_data') || '{}') }));
    }
}, []);
```
