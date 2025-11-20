# Análisis de Completitud y Preparación para Producción - ZenzSpa Backend

# FALTA:



Informe completado; la base luce madura pero todavía arrastra huecos importantes para estar en producción. Calificación global (excluyendo bot y pruebas): 6/10.

Panorama General (6/10 sin bot)

Arquitectura y configuración son consistentes, pero hay piezas desconectadas: el handler personalizado de errores REST nunca se registra, las respuestas seguirán saliendo en el formato por defecto (zenzspa/settings.py:69-121; core/exceptions.py:22-68). Corrección: agregar REST_FRAMEWORK["EXCEPTION_HANDLER"] = "core.exceptions.drf_exception_handler" y validar que los clientes reciben la nueva estructura.
Los scopes de throttling definidos (auth_login/auth_verify/payments/bot) no se usan porque ninguna vista fija throttle_scope, de modo que OTP, pagos y reportes solo dependen del rate global (zenzspa/settings.py:86-111). Corrección: añadir throttle_scope en cada vista sensible (por ejemplo VerifySMSView.throttle_scope = "auth_verify").
Se versionaron los archivos celerybeat-schedule*; al desplegar, Celery Beat pensará que ya ejecutó tareas y ignorará nuevos cron jobs. Corrección: eliminarlos del repo y añadirlos al .gitignore.

### Usuarios – 6/10

El endpoint de verificación por SMS emite tokens aunque el usuario esté inactivo o marcado como Persona Non Grata; basta con tener un código válido para volver a entrar (users/views.py:115-179). Corrección: antes de generar RefreshToken, validar user.is_active y not user.is_persona_non_grata; en caso contrario devolver 403 y auditar el intento.
OTP/registro/restablecimiento no están atados a los scopes de throttling específicos; con un solo AnonRateThrottle a 60/min siguen siendo fáciles de brute-forcear (users/views.py y PasswordReset*. views). Corrección: definir throttle_scope en las vistas (auth_login, auth_verify, auth_verify_reset) para usar las cuotas del settings, y documentar los límites en la API.

### Spa – 5/10

Cuando un anticipo se cubre parcialmente con créditos, PaymentService.create_advance_payment_for_appointment reescribe payment.amount con solo el remanente en efectivo (spa/services.py:1083-1147). Luego calculate_outstanding_amount suma ese monto reducido y nunca descuenta la parte pagada con créditos (spa/services.py:1171-1188), dejando citas con “saldo pendiente” inexistente y bloqueando su cierre. Corrección: mantener payment.amount en el valor completo requerido y restar explícitamente la suma de PaymentCreditUsage (o crear un registro separado para la porción cubierta por créditos) al calcular outstanding.
El cálculo de expiración de paquetes nuevos usa timezone.timedelta, atributo que no existe en django.utils.timezone, por lo que la primera compra con validity_days > 0 explota con AttributeError (spa/models.py:482-486). Corrección: usar la clase importada timedelta (self.purchase_date.date() + timedelta(days=...)).
El campo Payment.used_credit solo guarda el último crédito aplicado en un anticipo con múltiples créditos, perdiendo trazabilidad (spa/services.py:1117-1135). Corrección: convertirlo en relación many-to-many o calcular el crédito total a partir de PaymentCreditUsage cuando se necesite auditar.

### Perfiles – 6/10

Los tokens de sesión de quiosco se guardan en texto claro (secrets.token_hex(20)) y se reutilizan en cabecera X-Kiosk-Token; una filtración de BD permite secuestrar cualquier flujo en curso (profiles/models.py:252-310). Corrección: guardar solo un hash (por ejemplo SHA-256) del token y comparar hashes al validar.
ClinicalProfileAccessPermission devuelve True inmediatamente para sesiones de quiosco, sin restringir métodos; un cliente en kiosk podría enviar DELETE y borrar su perfil aunque la UI no lo exponga (profiles/permissions.py:8-40). Corrección: limitar los métodos permitidos para kiosk (por ejemplo sólo GET/PATCH) antes de conceder acceso.

### Marketplace – 7/10

El checkout construye el payload de pago aunque PaymentService._resolve_acceptance_token o la firma fallen; el front recibe acceptanceToken=None y la UX se rompe sin explicación (marketplace/views.py:202-220). Corrección: si no hay token o firma, revertir la orden recién creada y devolver 503/502 con mensaje claro.
Se expone cada orden reservada con reservation_expires_at, pero no se devuelve el carrito ni se notifica al usuario en caso de error durante OrderCreationService.create_order; envolver todo el bloque en un retry y devolver detalles del fallo ayudaría a evitar carritos huérfanos (marketplace/views.py:181-199).

### Notificaciones – 7/10

Se renderizan subject/body al momento de encolar; si la entrega se difiere por quiet hours, el contenido puede quedar desactualizado (por ejemplo, “tu cita es mañana” aunque el correo salga horas después) (notifications/services.py:74-92). Corrección: almacenar únicamente el contexto y volver a renderizar dentro de send_notification_task justo antes del envío.
El payload guardado en NotificationLog incluye los cuerpos completos sin sanitizar, lo que expone PII permanente en la base si hay incidentes (notifications/services.py:124-139). Corrección: guardar solo metadatos o cifrar/truncar los contenidos sensibles antes de persistirlos.

### Analytics – 6/10

Los filtros staff_id y service_category_id se convierten a int, pero tanto usuarios como categorías usan UUID; cualquier petición válida falla con “debe ser numérico” (analytics/views.py:63-74). Corrección: aceptar UUID (UUIDField/uuid.UUID) y filtrar por esos valores.
Algunos endpoints (por ejemplo dashboard/pending-payments) cargan todos los registros sin paginar y cachean la lista entera; con backlog grande pueden saturar memoria y Redis (analytics/views.py:162-212). Corrección: paginar resultados o limitar el dataset (p.ej. últimas N entradas) antes de cachear.

### Finanzas – 6/10

WompiDisbursementClient.create_payout no incluye cabecera/idempotency key; un retry del celery task podría disparar doble transferencia (finances/services.py:102-157). Corrección: enviar el header Idempotency-Key de Wompi y registrar la referencia para detectar duplicados.
Ante un fallo al consultar saldo, _attempt_payout cae en _mark_failed_nsf() y marca todas las comisiones como “FAILED_NSF” aunque el error sea de red o autenticación (finances/services.py:182-230). Corrección: distinguir entre errores de comunicación y falta real de fondos, registrando el detalle y dejando los asientos en PENDING para reintento automático.



# ANALISIS 2:


Improvements by Module (Critical → Minor)
core
Security: Ensure all admin endpoints enforce strict permission checks; some views lack explicit IsAdminUser.
Error handling: Convert generic ValidationError messages to standardized error codes (RFD‑APP‑002).
Performance: Replace heavy queryset loops in 
SoftDeleteQuerySet
 with bulk updates where possible.
Documentation: Add OpenAPI specs for all API endpoints.
analytics
Missing push notifications: Integrate real‑time notification service (e.g., Firebase) for KPI alerts.
Export formats: Add XLSX export alongside CSV for better reporting.
Cache invalidation: Ensure analytics caches are cleared after data‑changing operations.
bot
Incomplete flows: Implement missing re‑schedule, policies, and price flows.
Security: Add role‑based access control to bot endpoints; currently no explicit checks.
Logging: Persist BotInteraction records for auditability.
Performance: Optimize Gemini calls with response caching.
finances
Recurring VIP payments: Complete integration with Wompi subscriptions for true recurring billing.
Error codes: Standardize API error responses for payment failures.
Idempotency: Verify all payment endpoints are idempotent.
marketplace
Stock reservation: Reserve inventory at checkout rather than only on payment confirmation.
Notification: Add email/push notifications for low‑stock alerts.
Performance: Index ProductVariant fields used in frequent queries.
notifications
Missing channels: Implement push notifications (Firebase/OneSignal) alongside email/SMS.
Granular opt‑out: Allow users to disable specific event types, not just whole channels.
Audit: Log every notification sent to NotificationLog.
profiles
Kiosk security: Harden kiosk session middleware to prevent session fixation.
Data masking: Ensure 
DataMaskingMixin
 covers all sensitive fields across serializers.
Consent handling: Add versioning and expiry for consent documents.
spa
UI/UX: Apply modern design patterns (glassmorphism, dark mode) to improve user experience.
Performance: Lazy‑load heavy components and enable HTTP/2 compression.
Accessibility: Add ARIA labels and keyboard navigation support.
users
Device session tracking: Auto‑create UserSession on login; currently manual.
Token revocation: Ensure refresh token blacklist works for all logout flows.
Password policies: Enforce stronger password complexity.
zenzspa (global settings)
Validation: Add model‑level validators for all numeric fields to prevent out‑of‑range values.
Cache consistency: Invalidate GLOBAL_SETTINGS_CACHE_KEY on every update.
Documentation: Provide admin UI for editing global settings safely.
Summary
Overall the codebase is solid with functionality scores averaging 8‑9/10. Security and efficiency are generally good but have notable gaps, especially around push notifications, standardized error handling, and some incomplete business flows. Addressing the critical items above will bring the system to a more robust, secure, and performant state.