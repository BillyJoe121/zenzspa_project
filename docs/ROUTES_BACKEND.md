# Rutas expuestas por el backend

Base de servicio (desarrollo Docker): `http://localhost:8000`

## Infraestructura
- `/admin/` – Panel de Django.
- `/metrics/` – Métricas Prometheus.
- `/health/` – Health check.

## Autenticación y usuarios (`/api/v1/auth/`)
- `otp/request/` – Solicita OTP de registro.
- `otp/confirm/` – Confirma OTP y entrega JWT.
- `token/` – Obtener JWT (login).
- `token/refresh/` – Refrescar JWT.
- `logout/`, `logout_all/`
- `password/change/`
- `password-reset/request/`, `password-reset/confirm/`
- `me/` – Perfil del usuario autenticado.
- `me/delete/`
- `staff/` – Lista de staff.
- `sessions/`, `sessions/<uuid:id>/` – Sesiones activas.
- `totp/setup/`, `totp/verify/`
- `email/verify/`
- `admin/block-ip/`
- `admin/flag-non-grata/<str:phone_number>/`
- `admin/export/`
- `admin/users/` – CRUD admins (list/create/retrieve/update/delete).

## Bot (`/api/v1/bot/`)
- `webhook/`
- `whatsapp/`
- `health/`
- `analytics/`
- `suspicious-users/`
- `activity-timeline/`
- `block-ip/`, `unblock-ip/`
- `task-status/<str:task_id>/`
- `handoffs/` – CRUD handoffs (router).

## Analytics (`/api/v1/analytics/`)
- `kpis/`
- `kpis/export/`
- `kpis/time-series/`
- `cache/clear/`
- `dashboard/` – CRUD dashboards.
- `ops/` – CRUD vistas operativas.
- `bi/` – CRUD vistas BI.

## Finanzas (`/api/v1/finances/`)
- `commissions/`
- `commissions/status/`
- `pse-banks/`
- `payments/appointment/<uuid:pk>/initiate/`
- `payments/vip-subscription/initiate/`
- `payments/package/initiate/`
- `payments/<uuid:pk>/pse/`
- `payments/<uuid:pk>/nequi/`
- `payments/<uuid:pk>/daviplata/`
- `payments/<uuid:pk>/bancolombia-transfer/`
- `webhooks/wompi/`
- `admin/credits/` – CRUD créditos admin.

## Marketplace (`/api/v1/marketplace/`)
- `products/` – Listado y detalle público.
- `cart/` – CRUD carrito del usuario.
- `orders/` – Historial de órdenes (lectura) y detalle.
- `reviews/` – CRUD reseñas.
- Admin: `admin/products/`, `admin/variants/`, `admin/product-images/`, `admin/inventory-movements/`, `admin/orders/`.

## Catálogo SPA (`/api/v1/catalog/`)
- `service-categories/` – CRUD categorías.
- `services/` – CRUD servicios.
- `packages/` – CRUD paquetes.

## Citas y paquetes (`/api/v1/`)
- `appointments/` – CRUD citas.
- `staff-availability/` – Disponibilidad de staff.
- `my-packages/` – Paquetes del usuario.
- `my-vouchers/` – Vouchers del usuario.
- Admin: `admin/vouchers/`, `admin/packages/`.
- `availability/blocks/`
- `vip/cancel-subscription/`
- `financial-adjustments/`
- `history/` – Historial de citas del cliente.

## Perfiles clínicos (`/api/v1/`)
- Router:
  - `users/` – CRUD perfil clínico (por usuario).
  - `clinical-history/` – Histórico clínico.
  - `dosha-questions-admin/` – CRUD preguntas Dosha (admin).
  - `consent-templates/` – CRUD plantillas de consentimiento.
- Rutas adicionales:
  - `dosha-quiz/`, `dosha-quiz/submit/`
  - `kiosk/start/`, `kiosk/status/`, `kiosk/heartbeat/`, `kiosk/lock/`, `kiosk/discard/`, `kiosk/secure-screen/`, `kiosk/pending-changes/`
  - `anonymize/<str:phone_number>/`
  - `consents/sign/`
  - `consents/revoke/<uuid:consent_id>/`
  - `export/`

## Notificaciones (`/api/v1/notifications/`)
- `preferences/me/`

## Legal (`/api/v1/legal/`)
- `documents/` – CRUD documentos legales (público/lectura según permisos).
- `consents/` – CRUD consentimientos de usuario.
- `admin/documents/` – CRUD documentos (admin).

---

## Flujos clave (login, registro OTP, password reset)

### Login JWT (`POST /api/v1/auth/token/`)
- Request body: `phone_number` (E.164, ej. `+573001112233`), `password`; si hubo ≥5 intentos fallidos en 1h, también `recaptcha_token`.
- Respuesta exitosa: `200` con `access`, `refresh`, `role`.
- Efecto en DB: registra/actualiza `UserSession` con `refresh jti`, IP, User-Agent.
- Errores comunes:
  - `400`: formato de teléfono inválido o campos faltantes.
  - `401`: credenciales incorrectas.
  - `400`: `{"detail": "El número de teléfono no ha sido verificado..."}` si `is_verified=False`.
  - `403`: dispositivo bloqueado (`{"detail": "Tu dispositivo ha sido bloqueado..."}`).
  - `400`: `{"detail": "Completa reCAPTCHA para continuar."}` si excede intentos y falta `recaptcha_token`.

### Registro OTP (2 pasos)
1) **Solicitar OTP** (`POST /api/v1/auth/otp/request/`)
   - Request: `phone_number`, `password`, `first_name`, `last_name`, `email` opcional; si heurística de riesgo, `recaptcha_token`.
   - Respuesta exitosa: `201` con datos mínimos del usuario (sin tokens); se envía SMS vía Twilio.
   - Efecto en DB: crea usuario `is_verified=False`, crea `ClinicalProfile` y `NotificationPreference`.
   - Errores:
     - `400`: teléfono duplicado, bloqueado o formato inválido.
     - `400`: `{"recaptcha_token": "Se requiere verificación..."}` si falta reCAPTCHA requerido.
2) **Confirmar OTP** (`POST /api/v1/auth/otp/confirm/`)
   - Request: `phone_number`, `code`; si supera umbral de intentos, `recaptcha_token`.
   - Respuesta exitosa: `200` con `access`, `refresh`, `detail`.
   - Efecto en DB: marca `is_verified=True`, registra `UserSession`, limpia contadores de intentos.
   - Errores:
     - `400`: código inválido/expirado.
     - `404`: usuario no encontrado para ese teléfono.
     - `429`: demasiados intentos (mensaje indica minutos de espera).
     - `403`: IP bloqueada (key `blocked_ip`).
     - `400`: requiere reCAPTCHA.

### Password reset
- Solicitar: `POST /api/v1/auth/password-reset/request/` (envía token/código vía canal definido).
  - Errores: `404` si usuario no existe (según implementación), `400` si falta el identificador.
- Confirmar: `POST /api/v1/auth/password-reset/confirm/` con token/código de reset y nueva `password`.
  - Respuesta: `200` al actualizar la contraseña.
  - Luego debes hacer login de nuevo en `token/`.

### Reglas generales
- El backend **no agrega prefijo**: envía siempre el número ya en E.164 (`+57...`).
- Muchos endpoints requieren JWT; sólo los de OTP y password reset son públicos.
- Si Prometheus golpea `/metrics` con host `web:8000`, agrega `web` a `ALLOWED_HOSTS` para evitar `DisallowedHost`.
