# Variables Configurables del Sistema StudioZens

Esta es la lista completa de todas las variables y configuraciones que el backend permite modificar desde el frontend. Están organizadas por categoría y modelo.

---

## 📊 1. GlobalSettings (Configuración Global del Sistema)

**Modelo:** `core.models.GlobalSettings`  
**Endpoint:** `/api/v1/core/settings/` (necesita implementarse)  
**Permisos:** Solo ADMIN

### 1.1 Configuración de Citas

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `low_supervision_capacity` | Integer | 1 | Número máximo de citas de baja supervisión simultáneas | ≥ 1 |
| `advance_payment_percentage` | Integer | 40 | Porcentaje de anticipo requerido (%) | 0-100 |
| `appointment_buffer_time` | Integer | 10 | Tiempo de limpieza entre citas (minutos) | ≤ 180 |
| `advance_expiration_minutes` | Integer | 20 | Tiempo para pagar anticipo antes de cancelar automáticamente | ≥ 1 |

### 1.2 Configuración VIP y Lealtad

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `vip_monthly_price` | Decimal | 0 | Precio mensual de suscripción VIP (COP) | ≥ 0 |
| `loyalty_months_required` | Integer | 3 | Meses continuos como VIP para recompensa | ≥ 1 |
| `loyalty_voucher_service` | ForeignKey | null | Servicio otorgado como voucher de lealtad | Debe existir |

### 1.3 Configuración de Créditos y Devoluciones

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `credit_expiration_days` | Integer | 365 | Días de vigencia para créditos | ≥ 1 |
| `return_window_days` | Integer | 30 | Días máximos para aceptar devoluciones | ≥ 0 |
| `no_show_credit_policy` | Choice | NONE | Política de crédito para No-Show | NONE/PARTIAL/FULL |

**Opciones de `no_show_credit_policy`:**
- `NONE`: Sin crédito
- `PARTIAL`: Crédito parcial (50%)
- `FULL`: Crédito total (100%)

### 1.4 Configuración de Notificaciones

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `quiet_hours_start` | Time | null | Hora de inicio de silencio de notificaciones | HH:MM |
| `quiet_hours_end` | Time | null | Hora de fin de silencio de notificaciones | HH:MM |
| `timezone_display` | String | "America/Bogota" | Zona horaria para mostrar fechas | Timezone válido |

### 1.5 Configuración de Lista de Espera

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `waitlist_enabled` | Boolean | False | Activar/desactivar módulo de lista de espera | - |
| `waitlist_ttl_minutes` | Integer | 60 | Tiempo máximo para responder oferta de lista de espera | ≥ 5 |

### 1.6 Configuración de Comisiones (Desarrollador)

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `developer_commission_percentage` | Decimal | 5.00 | Comisión del desarrollador (%) | \u003e 0, solo puede aumentar |
| `developer_payout_threshold` | Decimal | 200000.00 | Saldo mínimo antes de dispersión (COP) | \u003e 0 |
| `developer_in_default` | Boolean | False | Sistema adeuda pagos al desarrollador | - |
| `developer_default_since` | DateTime | null | Fecha de inicio de mora | - |

---

## 🤖 2. BotConfiguration (Configuración del Chatbot)

**Modelo:** `bot.models.BotConfiguration`  
**Endpoint:** `/api/v1/bot/config/` (necesita implementarse)  
**Permisos:** Solo ADMIN

### 2.1 Información General

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `site_name` | String | "Studio Zens" | Nombre del sitio | Max 100 chars |
| `booking_url` | URL | "https://www.studiozens.com/agendar" | URL de agendamiento | URL válida |
| `admin_phone` | String | "+57 0" | Teléfono de contacto admin | Formato internacional |
| `is_active` | Boolean | True | Bot activo/inactivo | - |

### 2.2 Prompt del Sistema

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `system_prompt_template` | Text | (Ver modelo) | Plantilla del prompt del bot | Debe contener variables requeridas |

**Variables requeridas en el prompt:**
- `{{ user_message }}`
- `{{ services_context }}`
- `{{ products_context }}`
- `{{ booking_url }}`
- `{{ admin_phone }}`
- `{{ client_context }}`
- `{{ staff_context }}`

### 2.3 Configuración de Costos API (Gemini)

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `api_input_price_per_1k` | Decimal | 0.0001 | Precio input USD/1K tokens | ≥ 0 |
| `api_output_price_per_1k` | Decimal | 0.0004 | Precio output USD/1K tokens | ≥ 0 |
| `daily_cost_alert_threshold` | Decimal | 0.33 | Umbral de alerta diaria (USD) | ≥ 0 |
| `avg_tokens_alert_threshold` | Integer | 2000 | Umbral de tokens promedio | ≥ 0 |

### 2.4 Configuración de Seguridad del Bot

| Campo | Tipo | Default | Descripción | Validación |
|-------|------|---------|-------------|------------|
| `enable_critical_alerts` | Boolean | True | Enviar alertas de seguridad críticas | - |
| `enable_auto_block` | Boolean | True | Bloqueo automático de IPs abusivas | - |
| `auto_block_critical_threshold` | Integer | 3 | Actividades críticas antes de bloquear | ≥ 1 |
| `auto_block_analysis_period_hours` | Integer | 24 | Ventana de tiempo para análisis (horas) | ≥ 1 |

---

## 👥 3. Gestión de Staff (Terapeutas)

**Modelo:** `users.models.CustomUser` (role=STAFF)  
**Endpoint:** `/api/v1/users/` (filtrar por role=STAFF)  
**Permisos:** ADMIN

### 3.1 Información del Terapeuta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `phone_number` | String | Teléfono (único, requerido) |
| `email` | String | Email (opcional) |
| `first_name` | String | Nombre |
| `last_name` | String | Apellido |
| `role` | Choice | Debe ser 'STAFF' |
| `is_active` | Boolean | Activo/Inactivo |

### 3.2 Horarios de Disponibilidad

**Modelo:** `spa.models.StaffAvailability`  
**Endpoint:** `/api/v1/spa/staff-availability/`  
**Permisos:** ADMIN

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `staff_member` | ForeignKey | Terapeuta asignado | Debe ser STAFF/ADMIN |
| `day_of_week` | Integer | Día de la semana (1-7) | 1=Lunes, 7=Domingo |
| `start_time` | Time | Hora de inicio | \u003c end_time |
| `end_time` | Time | Hora de fin | \u003e start_time |

### 3.3 Exclusiones de Disponibilidad

**Modelo:** `spa.models.AvailabilityExclusion`  
**Endpoint:** `/api/v1/spa/availability-exclusions/` (necesita implementarse)  
**Permisos:** ADMIN

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `staff_member` | ForeignKey | Terapeuta | Debe ser STAFF/ADMIN |
| `date` | Date | Fecha específica (opcional) | - |
| `day_of_week` | Integer | Día recurrente (opcional) | 1-7 |
| `start_time` | Time | Hora de inicio | \u003c end_time |
| `end_time` | Time | Hora de fin | \u003e start_time |
| `reason` | String | Motivo del bloqueo | Max 255 chars |

---

## 🛍️ 4. Gestión de Servicios

**Modelo:** `spa.models.Service`  
**Endpoint:** `/api/v1/spa/services/` (necesita implementarse)  
**Permisos:** ADMIN

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `name` | String | Nombre del servicio | Max 255 chars |
| `description` | Text | Descripción detallada | - |
| `duration` | Integer | Duración en minutos | \u003e 0 |
| `price` | Decimal | Precio regular (COP) | ≥ 0 |
| `vip_price` | Decimal | Precio VIP (COP) | \u003c price |
| `category` | ForeignKey | Categoría del servicio | Debe existir |
| `is_active` | Boolean | Servicio disponible | - |

---

## 🏷️ 5. Gestión de Categorías de Servicios

**Modelo:** `spa.models.ServiceCategory`  
**Endpoint:** `/api/v1/spa/service-categories/` (necesita implementarse)  
**Permisos:** ADMIN

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `name` | String | Nombre de la categoría | Max 100 chars, único |
| `description` | Text | Descripción | - |
| `is_low_supervision` | Boolean | Permite múltiples citas simultáneas | - |

---

## 🛒 6. Gestión de Productos (Marketplace)

**Modelo:** `marketplace.models.Product`  
**Endpoint:** `/api/v1/marketplace/products/` (necesita implementarse)  
**Permisos:** ADMIN

### 6.1 Información del Producto

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `name` | String | Nombre del producto | Max 255 chars |
| `description` | Text | Descripción detallada | - |
| `category` | ForeignKey | Categoría del producto | Debe existir |
| `is_active` | Boolean | Producto visible | - |

### 6.2 Variantes de Producto

**Modelo:** `marketplace.models.ProductVariant`

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `product` | ForeignKey | Producto padre | Debe existir |
| `sku` | String | Código único | Único |
| `price` | Decimal | Precio regular (COP) | ≥ 0 |
| `vip_price` | Decimal | Precio VIP (COP) | \u003c price |
| `stock` | Integer | Inventario disponible | ≥ 0 |
| `low_stock_threshold` | Integer | Umbral de alerta de stock bajo | ≥ 0 |

---

## 📝 7. Gestión de Blog

**Modelo:** `blog.models.BlogPost`  
**Endpoint:** `/api/v1/blog/posts/` (necesita implementarse)  
**Permisos:** ADMIN

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `title` | String | Título del post | Max 200 chars |
| `slug` | String | URL amigable | Único |
| `content` | Text | Contenido HTML/Markdown | - |
| `excerpt` | Text | Resumen corto | - |
| `author` | ForeignKey | Usuario autor | Debe ser STAFF/ADMIN |
| `status` | Choice | Estado del post | DRAFT/PUBLISHED/ARCHIVED |
| `published_at` | DateTime | Fecha de publicación | - |
| `featured_image` | Image | Imagen destacada | - |
| `meta_description` | String | SEO meta description | Max 160 chars |
| `tags` | ManyToMany | Etiquetas del post | - |

---

## 🏢 8. Página "Quiénes Somos"

**Modelo:** `core.models.AboutPage` (necesita crearse)  
**Endpoint:** `/api/v1/core/about/` (necesita implementarse)  
**Permisos:** ADMIN

**Campos sugeridos:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `mission` | Text | Misión de la empresa |
| `vision` | Text | Visión de la empresa |
| `values` | Text | Valores corporativos |
| `history` | Text | Historia de StudioZens |
| `team_description` | Text | Descripción del equipo |
| `hero_image` | Image | Imagen principal |
| `gallery_images` | ManyToMany | Galería de fotos |

---

## 🔐 9. Variables de Entorno (Backend)

**Archivo:** `.env`  
**Acceso:** Solo servidor, NO exponer al frontend  
**Gestión:** SSH/Panel de control del servidor

### 9.1 APIs Externas

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `GEMINI_API_KEY` | API Key de Google Gemini | `AIza...` |
| `GEMINI_MODEL` | Modelo de Gemini a usar | `gemini-2.5-flash-lite` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `...` |
| `TWILIO_VERIFY_SERVICE_SID` | Twilio Verify Service | `VA...` |
| `WOMPI_PUBLIC_KEY` | Wompi Public Key | `pub_test_...` |
| `WOMPI_PRIVATE_KEY` | Wompi Private Key | `prv_test_...` |
| `WOMPI_INTEGRITY_SECRET` | Wompi Integrity Secret | `...` |

### 9.2 Configuración de Sistema

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DEBUG` | Modo debug | `0` (False) |
| `SECRET_KEY` | Django secret key | - |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost` |
| `SITE_URL` | URL del sitio | `http://localhost:8000` |
| `REDIS_URL` | URL de Redis | `redis://127.0.0.1:6379/1` |

### 9.3 JWT y Sesiones

| Variable | Descripción | Default |
|----------|-------------|---------|
| `JWT_ACCESS_MIN` | Duración Access Token (min) | `15` |
| `JWT_REFRESH_DAYS` | Duración Refresh Token (días) | `90` |

### 9.4 Throttling (Rate Limiting)

| Variable | Descripción | Default |
|----------|-------------|---------|
| `THROTTLE_USER` | Límite usuarios autenticados | `100/min` |
| `THROTTLE_ANON` | Límite usuarios anónimos | `30/min` |
| `THROTTLE_AUTH_LOGIN` | Límite login | `3/min` |
| `THROTTLE_BOT` | Límite bot | `15/min` |
| `THROTTLE_PAYMENTS` | Límite pagos | `30/min` |

---

## 📊 Resumen de Endpoints Necesarios

### ✅ Ya Implementados
- `/api/v1/analytics/kpis/`
- `/api/v1/analytics/dashboard/*`
- `/api/v1/spa/appointments/`
- `/api/v1/spa/staff-availability/`
- `/api/v1/users/`

### ❌ Por Implementar
- `/api/v1/core/settings/` (GlobalSettings CRUD)
- `/api/v1/bot/config/` (BotConfiguration CRUD)
- `/api/v1/spa/services/` (Services CRUD)
- `/api/v1/spa/service-categories/` (ServiceCategory CRUD)
- `/api/v1/spa/availability-exclusions/` (AvailabilityExclusion CRUD)
- `/api/v1/marketplace/products/` (Products CRUD)
- `/api/v1/marketplace/product-variants/` (ProductVariant CRUD)
- `/api/v1/blog/posts/` (BlogPost CRUD)
- `/api/v1/core/about/` (AboutPage CRUD - modelo por crear)

---

## 🎨 Pantallas de Admin Sugeridas

### Dashboard Principal (Ya documentado)
- KPIs del día
- Agenda
- Pagos pendientes
- Alertas

### Configuración General
- **GlobalSettings**: Formulario con tabs por categoría
- **BotConfiguration**: Editor de prompt + configuración de seguridad

### Gestión de Personal
- **Lista de Staff**: Tabla con búsqueda
- **Horarios**: Calendario visual para asignar/modificar
- **Exclusiones**: Formulario para bloquear fechas/horarios

### Gestión de Servicios
- **Servicios**: CRUD con categorías
- **Categorías**: Gestión simple

### Gestión de Productos
- **Productos**: CRUD con variantes
- **Inventario**: Vista de stock con alertas

### Gestión de Contenido
- **Blog**: Editor WYSIWYG
- **Quiénes Somos**: Editor de página estática

### Métricas y Reportes
- **Analytics**: Gráficos y exportación
- **Costos de Bot**: Dashboard de uso de Gemini

---

## 🔒 Notas de Seguridad

1. **Nunca exponer** variables de entorno al frontend
2. **Validar permisos** en cada endpoint (IsAdmin)
3. **Auditar cambios** críticos (GlobalSettings, BotConfiguration)
4. **Rate limiting** en endpoints de configuración
5. **Caché invalidation** automática al modificar configuraciones
