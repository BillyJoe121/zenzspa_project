# 🌐 ARQUITECTURA COMPLETA - STUDIOZENS.COM

**Dominio**: studiozens.com  
**Objetivo**: Configurar backend (Django) y frontend (React/Next.js/etc.)

---

## 🎯 ARQUITECTURA RECOMENDADA

```
┌─────────────────────────────────────────────────────────────┐
│                     STUDIOZENS.COM                          │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ studiozens   │    │ api.studio   │    │ admin.studio │
│   .com       │    │  zens.com    │    │  zens.com    │
│              │    │              │    │              │
│  FRONTEND    │    │   BACKEND    │    │  DJANGO      │
│  (React/     │◄───┤   (Django    │    │  ADMIN       │
│   Next.js)   │    │    API)      │    │  (mismo      │
│              │    │              │    │   backend)   │
│  Vercel/     │    │   Render     │    │   Render     │
│  Netlify     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 📋 CONFIGURACIÓN COMPLETA PARA STUDIOZENS.COM

### **Opción 1: Frontend y Backend Separados** (RECOMENDADO)

Esta es la configuración más profesional y escalable:

#### **Frontend** → `studiozens.com` y `www.studiozens.com`
- Aplicación React/Next.js/Vue
- Desplegado en Vercel, Netlify, o Render
- Los usuarios acceden aquí directamente

#### **Backend API** → `api.studiozens.com`
- Django REST API
- Desplegado en Render
- El frontend hace requests a esta URL

#### **Admin Panel** → `admin.studiozens.com` (opcional)
- Django Admin
- Mismo backend, solo diferente URL
- Solo para staff/admins

---

## 🔧 CONFIGURACIÓN DNS EN GODADDY

### Para Backend + Frontend Separados

```
┌──────────┬─────────┬──────────────────────────────────┬──────────┐
│   Type   │  Name   │            Value                 │   TTL    │
├──────────┼─────────┼──────────────────────────────────┼──────────┤
│ CNAME    │ api     │ studiozens-web.onrender.com         │ 1 Hour   │
│ CNAME    │ admin   │ studiozens-web.onrender.com         │ 1 Hour   │
│ CNAME    │ www     │ studiozens.com                   │ 1 Hour   │
│ A        │ @       │ [IP de tu hosting frontend]      │ 1 Hour   │
└──────────┴─────────┴──────────────────────────────────┴──────────┘
```

**Explicación**:
- `api.studiozens.com` → Apunta a tu backend en Render
- `admin.studiozens.com` → Apunta al mismo backend (Django admin)
- `www.studiozens.com` → Redirect al dominio principal
- `studiozens.com` → Tu frontend (la IP depende de dónde lo despliegues)

---

## 🚀 OPCIONES PARA DESPLEGAR EL FRONTEND

### **Opción A: Vercel** (RECOMENDADO - GRATIS)

**Ventajas**:
- ✅ GRATIS para proyectos personales
- ✅ SSL automático
- ✅ Deploy automático desde GitHub
- ✅ Optimizado para Next.js/React
- ✅ CDN global

**Pasos**:
1. Crear cuenta en vercel.com
2. Conectar repositorio de GitHub (frontend)
3. Deploy automático
4. En Vercel: Settings → Domains → Add `studiozens.com`
5. Vercel te dará instrucciones DNS

**DNS en GoDaddy** (Vercel te dará estos valores):
```
Type: A
Name: @
Value: 76.76.21.21  (IP de Vercel)
TTL: 1 Hour

Type: CNAME
Name: www
Value: cname.vercel-dns.com
TTL: 1 Hour
```

---

### **Opción B: Netlify** (GRATIS)

Similar a Vercel, también excelente para frontend.

**DNS en GoDaddy**:
```
Type: A
Name: @
Value: 75.2.60.5  (IP de Netlify)
TTL: 1 Hour

Type: CNAME
Name: www
Value: [tu-sitio].netlify.app
TTL: 1 Hour
```

---

### **Opción C: Render** (Mismo servicio que backend)

**Ventajas**:
- ✅ Todo en un solo lugar
- ✅ Fácil de gestionar

**Desventajas**:
- ❌ Más caro que Vercel/Netlify para frontend
- ❌ No tan optimizado para frontend

**Costo**: $7/mes adicional

---

### **Opción D: GitHub Pages** (GRATIS pero limitado)

Solo para sitios estáticos simples.

---

## 📝 CONFIGURACIÓN PASO A PASO

### **PASO 1: Configurar Backend** (api.studiozens.com)

#### En Render:
```
Dashboard → studiozens-web → Settings → Custom Domains
→ Add: api.studiozens.com
→ Add: admin.studiozens.com
```

#### En GoDaddy:
```
DNS Management → Add

Record 1:
Type: CNAME
Name: api
Value: studiozens-web.onrender.com
TTL: 1 Hour

Record 2:
Type: CNAME
Name: admin
Value: studiozens-web.onrender.com
TTL: 1 Hour
```

#### Variables de Entorno en Render:
```bash
ALLOWED_HOSTS=studiozens-web.onrender.com,api.studiozens.com,admin.studiozens.com,studiozens.com,www.studiozens.com

CSRF_TRUSTED_ORIGINS=https://studiozens-web.onrender.com,https://api.studiozens.com,https://admin.studiozens.com,https://studiozens.com,https://www.studiozens.com

CORS_ALLOWED_ORIGINS=https://studiozens.com,https://www.studiozens.com

WOMPI_REDIRECT_URL=https://studiozens.com/payment-result
```

---

### **PASO 2: Configurar Frontend** (studiozens.com)

#### Opción: Vercel (RECOMENDADO)

1. **Crear proyecto en Vercel**:
   ```
   vercel.com → New Project → Import Git Repository
   Seleccionar tu repo de frontend
   ```

2. **Configurar build**:
   ```
   Framework: Next.js / React / Vite (según tu proyecto)
   Build Command: npm run build
   Output Directory: dist / build / .next
   ```

3. **Agregar dominio en Vercel**:
   ```
   Settings → Domains → Add Domain
   → studiozens.com
   → www.studiozens.com
   ```

4. **Vercel te mostrará instrucciones DNS**

5. **En GoDaddy, agregar registros**:
   ```
   Type: A
   Name: @
   Value: 76.76.21.21  (IP que Vercel te proporcione)
   TTL: 1 Hour

   Type: CNAME
   Name: www
   Value: cname.vercel-dns.com
   TTL: 1 Hour
   ```

6. **Configurar variables de entorno en Vercel**:
   ```
   Settings → Environment Variables

   NEXT_PUBLIC_API_URL=https://api.studiozens.com
   NEXT_PUBLIC_WOMPI_PUBLIC_KEY=pub_prod_...
   ```

---

## 🔗 CÓMO SE COMUNICAN FRONTEND Y BACKEND

### En tu código de Frontend (React/Next.js):

```javascript
// .env.production
NEXT_PUBLIC_API_URL=https://api.studiozens.com

// En tu código
const API_URL = process.env.NEXT_PUBLIC_API_URL;

// Ejemplo: Login
async function login(phone, password) {
  const response = await fetch(`${API_URL}/api/v1/auth/login/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ phone_number: phone, password }),
  });
  
  const data = await response.json();
  return data;
}

// Ejemplo: Crear cita
async function createAppointment(token, appointmentData) {
  const response = await fetch(`${API_URL}/api/v1/appointments/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(appointmentData),
  });
  
  return response.json();
}
```

---

## 🎨 FLUJO COMPLETO DE USUARIO

```
1. Usuario visita: https://studiozens.com
   ↓
2. Frontend (React) se carga desde Vercel
   ↓
3. Usuario hace login
   ↓
4. Frontend hace POST a: https://api.studiozens.com/api/v1/auth/login/
   ↓
5. Backend (Django en Render) responde con JWT token
   ↓
6. Frontend guarda token en localStorage
   ↓
7. Usuario crea cita
   ↓
8. Frontend hace POST a: https://api.studiozens.com/api/v1/appointments/
   con header: Authorization: Bearer <token>
   ↓
9. Backend crea la cita y responde
   ↓
10. Frontend muestra confirmación
```

---

## 📊 RESUMEN DE CONFIGURACIÓN FINAL

### **URLs del Proyecto**:
```
Frontend (usuarios):     https://studiozens.com
Frontend (www):          https://www.studiozens.com → redirect a studiozens.com
Backend API:             https://api.studiozens.com
Django Admin:            https://admin.studiozens.com/admin/
```

### **Registros DNS en GoDaddy**:
```
Type    Name    Value                           TTL
A       @       76.76.21.21 (Vercel)            1 Hour
CNAME   www     cname.vercel-dns.com            1 Hour
CNAME   api     studiozens-web.onrender.com        1 Hour
CNAME   admin   studiozens-web.onrender.com        1 Hour
```

### **Servicios y Costos**:
```
Backend (Render):        $35/mes (Web + DB + Redis + Workers)
Frontend (Vercel):       $0 (GRATIS)
Dominio (GoDaddy):       ~$12/año
Total:                   ~$35/mes + $12/año
```

---

## 🧪 TESTING

### Verificar Backend:
```bash
# API
curl https://api.studiozens.com/api/v1/

# Admin
https://admin.studiozens.com/admin/
```

### Verificar Frontend:
```bash
# Página principal
https://studiozens.com

# Debe cargar tu aplicación React/Next.js
```

### Verificar Comunicación:
```javascript
// En consola del navegador (F12)
fetch('https://api.studiozens.com/api/v1/')
  .then(r => r.json())
  .then(console.log)

// Debe mostrar la respuesta de tu API
```

---

## ❓ PREGUNTAS FRECUENTES

### **¿Necesito un frontend separado?**

**Opción 1: SÍ** (Recomendado para apps modernas)
- Frontend: React/Next.js en Vercel (GRATIS)
- Backend: Django API en Render ($35/mes)
- Mejor experiencia de usuario (SPA)
- Más rápido y escalable

**Opción 2: NO** (Más simple pero menos moderno)
- Todo en Django (templates + API)
- Solo Render ($35/mes)
- Menos moderno, pero funcional

### **¿Puedo usar solo studiozens.com sin subdominios?**

Sí, pero no es recomendado. Podrías:
```
studiozens.com           → Frontend
studiozens.com/api/      → Backend (no recomendado)
```

Pero es mejor usar subdominios para separar frontend y backend.

### **¿Qué pasa si no tengo frontend todavía?**

Puedes empezar solo con el backend:
```
api.studiozens.com       → Backend API
admin.studiozens.com     → Django Admin
studiozens.com           → Página "Coming Soon" simple
```

Luego agregas el frontend cuando esté listo.

---

## 🚀 PRÓXIMOS PASOS

1. ✅ **Configurar backend** en `api.studiozens.com` (guía anterior)
2. ⏭️ **Decidir tecnología de frontend** (React, Next.js, Vue, etc.)
3. ⏭️ **Crear repositorio de frontend** en GitHub
4. ⏭️ **Desplegar frontend** en Vercel/Netlify
5. ⏭️ **Configurar DNS** para `studiozens.com`
6. ⏭️ **Conectar frontend con backend** (API calls)

---

## 📚 RECURSOS

- [Vercel Domains](https://vercel.com/docs/concepts/projects/domains)
- [Netlify Custom Domains](https://docs.netlify.com/domains-https/custom-domains/)
- [GoDaddy DNS Management](https://www.godaddy.com/help/manage-dns-680)

---

**¿Tienes frontend ya desarrollado o necesitas ayuda para crearlo?** 🤔
