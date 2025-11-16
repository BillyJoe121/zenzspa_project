# Evaluación de Módulos ZenzSpa - Análisis de Requerimientos Funcionales

**Fecha de Evaluación:** 2025-01-XX  
**Versión del Documento de Requerimientos:** v2.0 (12-08-2025)

---

## Resumen Ejecutivo

Este documento evalúa cada módulo del sistema ZenzSpa comparándolo con los Requerimientos Funcionales Documentados (RFD) especificados. Cada módulo recibe una calificación del 1 al 10, donde:
- **10**: Implementación completa y perfecta según RFD
- **7-9**: Implementación sólida con mejoras menores necesarias
- **4-6**: Implementación parcial, faltan funcionalidades importantes
- **1-3**: Implementación básica o ausente

---

## 4.1 Autenticación y Gestión de Usuarios

### Calificación General: **8/10**

#### RFD-AUTH-01 — Verificación de identidad por OTP (SMS) ⭐ **9/10**

**✅ Implementado:**
- Registro/login con OTP vía Twilio Verify
- Código de 6 dígitos (manejado por Twilio)
- Expiración a los 5 minutos (configurado en Twilio)
- Control de intentos (máx. 3 intentos por 10 min)
- Bloqueo y cooldown de 10 minutos
- Respuesta 429 cuando se excede el límite
- **reCAPTCHA implementado** en reintentos anómalos (`_requires_recaptcha`)
- **Registro de intentos en BD** (`OTPAttempt` model)
- Mensaje descriptivo con tiempo restante en minutos

**❌ Faltante:**
- **reCAPTCHA v3**: Actualmente usa reCAPTCHA v2, podría mejorarse a v3 para mejor UX

**Recomendaciones:**
1. Migrar a reCAPTCHA v3 para mejor experiencia de usuario
2. Considerar ajustar umbrales de reCAPTCHA según métricas de producción

---

#### RFD-AUTH-02 — Tokens JWT con rotación y blacklist ⭐ **9/10**

**✅ Implementado:**
- Access token de 15 minutos (configurable)
- Refresh token de 7 días (configurable)
- Rotación de refresh tokens
- Blacklist después de rotación
- Integración con `rest_framework_simplejwt.token_blacklist`
- **Endpoint `LogoutAllView` implementado** (`_revoke_all_sessions`)
- **Gestión de sesiones activas** (`UserSession` model con endpoints)

**❌ Faltante:**
- **Creación automática de sesión al autenticar**: No se crea `UserSession` automáticamente en el login

**Recomendaciones:**
1. Crear señal post_save o middleware para crear `UserSession` automáticamente al emitir tokens
2. Mejorar tracking de información del dispositivo (User-Agent parsing)

---

#### RFD-AUTH-03 — Roles/Permisos y filtrado de datos ⭐ **7/10**

**✅ Implementado:**
- Sistema de roles jerárquico: ADMIN > STAFF > VIP > CLIENT
- Permisos personalizados (`IsAdminUser`, `IsStaff`, `IsVerified`)
- Serializadores con campos dinámicos

**❌ Faltante:**
- **Enmascaramiento sistemático de datos sensibles**: No hay implementación explícita de enmascaramiento de teléfono/email según rol
- **Pruebas de autorización por endpoint**: No se evidencia documentación de pruebas
- **Control a nivel de serializador**: Existe infraestructura pero no se aplica consistentemente

**Recomendaciones:**
1. Implementar mixin `DataMaskingMixin` para serializadores que enmascare datos según rol
2. Crear tests de autorización para cada endpoint crítico
3. Documentar matriz de permisos por endpoint

---

#### RFD-AUTH-04 — Cliente No Grato (CNG) ⭐ **9/10**

**✅ Implementado:**
- Campo `is_persona_non_grata` en `CustomUser`
- Endpoint `FlagNonGrataView` con permisos ADMIN
- Cancelación automática de citas futuras
- Bloqueo de tokens activos
- Auditoría en `AuditLog`
- Operación atómica con `@transaction.atomic`

**❌ Faltante:**
- **Bloqueo de registro si teléfono coincide**: No se valida en el registro si el teléfono está marcado como CNG

**Recomendaciones:**
1. Agregar validación en `UserRegistrationView` para bloquear registros con teléfonos CNG
2. Considerar notificación a ADMINs cuando se intente registrar un CNG

---

#### RFD-AUTH-05 — Recuperación de contraseña (fallback) ⭐ **9/10**

**✅ Implementado:**
- Endpoints `PasswordResetRequestView` y `PasswordResetConfirmView`
- Flujo con OTP vía Twilio
- Actualización de contraseña
- **Invalidación de sesiones activas** (`_revoke_all_sessions`)
- **Obligación de reautenticación** (mensaje indica necesidad de reautenticación)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar notificación por email cuando se cambia la contraseña

---

#### RFD-AUTH-06 — Gestión de dispositivos/sesiones ⭐ **9/10**

**✅ Implementado:**
- Modelo `UserSession` con tracking de dispositivos
- Endpoints para listar y eliminar sesiones (`UserSessionListView`, `UserSessionDeleteView`)
- Integración con `OutstandingToken` y `BlacklistedToken`
- Revocación de sesiones individuales

**❌ Faltante:**
- **Creación automática de sesión al autenticar**: No se crea `UserSession` automáticamente

**Recomendaciones:**
1. Crear señal o middleware para crear `UserSession` automáticamente en el login
2. Mejorar parsing de User-Agent para mostrar información más descriptiva

---

## 4.2 Perfil Clínico del Cliente

### Calificación General: **8.5/10**

#### RFD-CLI-01 — Modelo clínico versionado y consentimiento ⭐ **9.5/10**

**✅ Implementado:**
- Modelo `ClinicalProfile` con campos completos (alergias, contraindicaciones, condiciones médicas)
- Versionado con `simple_history` (HistoricalRecords)
- Modelo `ConsentDocument` con firma y hash SHA256
- Modelo `ConsentTemplate` con versionado
- Permisos diferenciados (STAFF/ADMIN edición, CLIENT lectura propia)
- Trazabilidad con `changed_by` y `changed_at` (vía simple_history)
- **Anonimización implementada** (`anonymize()` method)
- Endpoint `AnonymizeProfileView` para ADMIN

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar endpoint para que CLIENT pueda ver historial de cambios propios

---

#### RFD-CLI-02 — Modo quiosco (recepción) ⭐ **8/10**

**✅ Implementado:**
- Modelo `KioskSession` con token y expiración
- Endpoint `KioskStartSessionView` para iniciar sesión
- Permiso `IsKioskSession` para validar tokens
- Timeout de 10 minutos (configurable)
- Desactivación de sesión después de uso
- Endpoint `KioskSessionHeartbeatView` para mantener sesión activa
- Endpoint `KioskSessionDiscardChangesView` para descartar cambios

**❌ Faltante:**
- **Bloqueo de navegación**: No hay middleware o mecanismo que bloquee navegación fuera del flujo del quiosco
- **Pantalla segura tras timeout**: No hay redirección automática a pantalla segura
- **Validación de cambios no guardados**: No se implementa validación explícita

**Recomendaciones:**
1. Implementar middleware de quiosco que bloquee navegación
2. Agregar endpoint de "pantalla segura" y redirección automática
3. Implementar validación de cambios pendientes en frontend

---

## 4.3 Servicios y Horarios

### Calificación General: **9/10**

#### RFD-SRV-01 — Catálogo de servicios y categorías ⭐ **9.5/10**

**✅ Implementado:**
- CRUD completo de categorías y servicios
- Atributos requeridos: `duration`, `price`, `vip_price`, `is_active`
- Protección de integridad referencial (no se puede eliminar categoría con servicios)
- Error 409 cuando se intenta eliminar categoría con servicios
- Persistencia de `price_at_purchase` en `AppointmentItem`
- **Validación de precios VIP** (`vip_price < price` en `Service.clean()`)
- Versionado con `simple_history`

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar soft delete con historial

---

#### RFD-SRV-02 — Disponibilidad/horarios del spa ⭐ **9/10**

**✅ Implementado:**
- Modelo `StaffAvailability` con bloques semanales
- **Validación explícita de solapamientos** (`StaffAvailability.clean()`)
- **Modelo `AvailabilityExclusion`** para bloques de descanso/almuerzo
- Capacidad simultánea (`low_supervision_capacity` en GlobalSettings)
- Servicio `AvailabilityService` que calcula slots disponibles
- Considera exclusiones en el cálculo de disponibilidad

**❌ Faltante:**
- **Error 422 específico para solapamientos**: La validación retorna ValidationError genérico

**Recomendaciones:**
1. Mejorar mensajes de error con código específico (SRV-002)
2. Considerar agregar validación de capacidad simultánea en tiempo real

---

## 4.4 Citas (Agenda)

### Calificación General: **8.5/10**

#### RFD-APP-01 — Creación idempotente con validación atómica ⭐ **9/10**

**✅ Implementado:**
- Validación de bloque laboral, solapes y buffer
- Bloqueo de concurrencia con `select_for_update()`
- Validación atómica en `AppointmentService.create_appointment_with_lock()`
- **Idempotency-Key implementado** (`@idempotent_view` decorator)
- **Modelo `IdempotencyKey`** para almacenar respuestas
- **Reintento con misma clave devuelve misma respuesta**

**❌ Faltante:**
- **Error 409 con código específico**: Los errores no tienen códigos específicos (APP-002, etc.)

**Recomendaciones:**
1. Implementar códigos de error estándar según RFD
2. Mejorar mensajes de error con códigos específicos

---

#### RFD-APP-02 — Asignación inteligente de terapeuta ⭐ **8.5/10**

**✅ Implementado:**
- Endpoint `suggestions` que lista STAFF disponibles
- Considera duración, buffer, bloqueos y capacidad
- Retorna lista vacía si no hay disponibilidad
- **Mensaje claro cuando no hay disponibilidad**

**❌ Faltante:**
- **Optimización de recomendación**: No hay algoritmo de "mejor terapeuta" basado en historial

**Recomendaciones:**
1. Implementar algoritmo de recomendación basado en preferencias del cliente
2. Considerar agregar scoring de terapeutas según historial

---

#### RFD-APP-03 — Límites de citas activas ⭐ **9.5/10**

**✅ Implementado:**
- Validación en `AppointmentService._validate_appointment_rules()`
- CLIENT: máx. 1 activa
- VIP: máx. 4 activas
- Error 422 cuando se excede el límite
- Recalcula límite inmediatamente al cambiar rol
- **Mensaje descriptivo** con cantidad de citas actuales

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar hacer límites configurables en GlobalSettings

---

#### RFD-APP-04 — Cancelación automática por no pago ⭐ **9/10**

**✅ Implementado:**
- Tarea Celery `cancel_unpaid_appointments()` programada
- **Usa `advance_expiration_minutes` de GlobalSettings**
- Cancela citas con `PENDING_ADVANCE` después del tiempo configurado
- Notificación a lista de espera
- Cambio de estado a `CANCELLED_BY_SYSTEM`

**❌ Faltante:**
- **Notificación al cliente cancelado**: Solo se notifica a lista de espera
- **Registro de evento en AuditLog**: No se crea registro

**Recomendaciones:**
1. Notificar al cliente sobre cancelación
2. Registrar evento en AuditLog

---

#### RFD-APP-05 — Momento Zen (multi-servicio) ⭐ **9.5/10**

**✅ Implementado:**
- Soporte para múltiples servicios en una cita
- Validación de continuidad de bloques (implícita en disponibilidad)
- Cálculo de duración total
- Un solo `Appointment` con múltiples `AppointmentItem`

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar validación explícita de que los servicios son consecutivos

---

#### RFD-APP-06 — Reagendamiento limitado de citas pagadas ⭐ **9/10**

**✅ Implementado:**
- Límite de 2 reagendamientos (`reschedule_count`)
- Validación de 24 horas antes
- STAFF/ADMIN pueden bypass con auditoría (logging)
- Endpoint `reschedule` funcional
- **Cliente no puede cancelar directamente** (validación en `cancel`)

**❌ Faltante:**
- **Excepciones auditadas para STAFF**: Se registra en log pero no en AuditLog

**Recomendaciones:**
1. Registrar excepciones de STAFF en AuditLog
2. Mejorar mensaje cuando cliente intenta cancelar cita pagada

---

#### RFD-APP-07 — Cancelación por ADMIN y reembolso ⭐ **8/10**

**✅ Implementado:**
- Endpoint `cancel_by_admin` con permisos ADMIN
- Cambio de estado a `CANCELLED_BY_ADMIN`
- Opción de marcar como `REFUNDED`
- Auditoría en AuditLog
- **Generación automática de ClientCredit** cuando se marca como REFUNDED
- **Motivo de cancelación** capturado en el request

**❌ Faltante:**
- **Proceso de reembolso manual**: No hay flujo explícito de reembolso a pasarela, solo cambio de estado

**Recomendaciones:**
1. Implementar flujo de reembolso con integración a pasarela (Wompi)
2. Considerar agregar campo para método de reembolso (crédito vs. reembolso)

---

#### RFD-APP-08 — No-show y política de crédito ⭐ **8.5/10**

**✅ Implementado:**
- Endpoint `mark_as_no_show` para STAFF/ADMIN
- Cambio de estado a `NO_SHOW`
- Auditoría en AuditLog
- **Conversión automática a crédito** según política (`no_show_credit_policy` en GlobalSettings)
- **Configuración de política** (`no_show_credit_policy`, `credit_expiration_days`)
- **Validación de tiempo** (solo se puede marcar si la hora ya pasó)

**❌ Faltante:**
- **Notificación automática**: No se notifica al cliente sobre el crédito generado

**Recomendaciones:**
1. Notificar al cliente sobre crédito generado
2. Considerar agregar validación de tiempo mínimo transcurrido desde hora de cita

---

#### RFD-APP-09 — Lista de espera ⭐ **9/10**

**✅ Implementado:**
- Modelo `WaitlistEntry` con estados
- Servicio `WaitlistService` con lógica FIFO
- Notificación cuando se libera slot
- Ventana de aceptación (30 minutos TTL)
- **Endpoint para unirse** (`waitlist_join`)
- **Endpoint para confirmar** (`waitlist_confirm`)
- **Ofrecer al siguiente si no confirma** (lógica de reciclaje)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar hacer TTL configurable en GlobalSettings

---

#### RFD-APP-10 — Exportar iCal (.ics) ⭐ **9.5/10**

**✅ Implementado:**
- Endpoint `ical` que genera archivo .ics
- Datos mínimos: servicio, fecha, duración, ubicación
- Formato válido text/calendar
- Descarga con Content-Disposition

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Agregar más campos opcionales al iCal (descripción, URL de cancelación)

---

#### RFD-APP-11 — Bloqueo por deuda ⭐ **9.5/10**

**✅ Implementado:**
- Método `has_pending_final_payment()` en CustomUser
- Validación en `AppointmentService._validate_appointment_rules()`
- Error 422 con mensaje descriptivo
- Bloqueo se levanta automáticamente al pagar
- **Detalle de deuda en error** (monto y fecha)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar endpoint para consultar deudas pendientes

---

## 4.5 Pagos, Paquetes y VIP

### Calificación General: **8/10**

#### RFD-PAY-01 — Integración con pasarela (Wompi) ⭐ **9/10**

**✅ Implementado:**
- Integración con Wompi para checkout
- Webhook `WompiWebhookView` con validación de firma SHA256
- Idempotencia por `wompi_reference` (transaction_id)
- Registro de eventos en `WebhookEvent`
- Actualización de estado de citas/órdenes
- **Reintentos/sondeo** (`check_pending_payments` task y `poll_pending_payment` method)
- **Manejo de estados DECLINED** (se guarda y limpia intentos)

**❌ Faltante:**
- **Registro de eventos de webhook**: Existe `WebhookEvent` pero podría mejorarse el tracking

**Recomendaciones:**
1. Mejorar métricas y alertas de webhooks fallidos
2. Considerar agregar dashboard de monitoreo de webhooks

---

#### RFD-PAY-02 — Precios VIP dinámicos ⭐ **9.5/10**

**✅ Implementado:**
- Cálculo dinámico en `AvailabilityService.total_price_for_user()`
- Persistencia de `price_at_purchase` en AppointmentItem
- Aplicación según `vip_expires_at` vigente
- Cambios de rol aplican en tiempo real
- **Validación de vigencia** en método `is_vip`

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar caché para cálculos de precios frecuentes

---

#### RFD-PAY-03 — Paquetes/Vouchers ⭐ **9/10**

**✅ Implementado:**
- Modelos `Package`, `UserPackage`, `Voucher`
- Redención sin nuevo pago
- Expiración configurable (`validity_days`)
- Control de saldo y usos
- Estados: AVAILABLE, REDEEMED, EXPIRED
- **Auditoría de redenciones** (en `Voucher.save()`)
- **Beneficios como meses VIP** (`grants_vip_months` se aplica automáticamente)

**❌ Faltante:**
- **Mensaje claro al vencer**: No hay notificación automática de vencimiento

**Recomendaciones:**
1. Implementar notificación de vencimiento de vouchers
2. Considerar agregar recordatorio antes de vencer

---

#### RFD-PAY-04 — Lealtad VIP automatizada ⭐ **8.5/10**

**✅ Implementado:**
- Campo `grants_vip_months` en Package
- Modelo `SubscriptionLog` para registro
- **Tarea programada** `check_vip_loyalty()` para verificar condiciones
- **Emisión automática de voucher** cuando se cumplen condiciones
- **Configuración de condiciones** (`loyalty_months_required`, `loyalty_voucher_service` en GlobalSettings)
- **Notificación** (implícita en sistema de notificaciones)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Mejorar notificación específica para beneficios de lealtad
2. Considerar agregar dashboard de lealtad

---

#### RFD-PAY-05 — Anticipo obligatorio ⭐ **9.5/10**

**✅ Implementado:**
- `advance_payment_percentage` en GlobalSettings
- Creación automática de Payment tipo ADVANCE
- Cálculo correcto del anticipo
- Aplicación de créditos disponibles
- **Validación de mínimo** (implícita en cálculo)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar validación explícita de monto mínimo de anticipo

---

#### RFD-PAY-06 — Conversión de anticipo a crédito ⭐ **8.5/10**

**✅ Implementado:**
- Modelo `ClientCredit` con estados
- **Expiración configurable** (`credit_expiration_days` en GlobalSettings)
- Aplicación automática en nuevos pagos
- **Conversión automática en cancelaciones** (en `cancel` y `mark_as_no_show`)
- **Reglas de conversión** (políticas en GlobalSettings)

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Considerar agregar notificación cuando se genera crédito

---

#### RFD-VIP-01 — Suscripción VIP recurrente ⭐ **7/10**

**✅ Implementado:**
- Endpoint para iniciar suscripción VIP
- Modelo `SubscriptionLog` para registro
- Actualización de rol y `vip_expires_at`
- Prorrateo de fechas (si ya es VIP, empieza después)
- **Tarea Celery** `process_recurring_subscriptions()` para cobros recurrentes
- **Reintentos ante fallo** (`vip_failed_payments` counter)
- **Cancelación del plan** (`CancelVipSubscriptionView`)
- **Degradación automática** (`downgrade_expired_vips` task)

**❌ Faltante:**
- **Cobro mensual recurrente real**: La tarea crea pagos pero no integra con Wompi subscriptions
- **Notificación de fallos**: No se notifica al usuario sobre fallos de cobro

**Recomendaciones:**
1. Integrar con Wompi subscriptions API para cobros recurrentes reales
2. Notificar al usuario sobre fallos y degradación
3. Mejorar lógica de reintentos con configuración

---

#### RFD-PAY-07 — Propinas (tips) ⭐ **9.5/10**

**✅ Implementado:**
- Endpoint `add_tip` en AppointmentViewSet
- Payment tipo TIP
- Validación de que la cita esté completada
- Registro correcto

**❌ Faltante:**
- **Reportes discriminan propinas**: No se evidencia en reportes de analytics

**Recomendaciones:**
1. Asegurar que reportes de analytics discriminen propinas
2. Considerar agregar filtro de propinas en reportes

---

#### RFD-PAY-08 — Notas de débito/crédito internas ⭐ **9/10**

**✅ Implementado:**
- Modelo `FinancialAdjustment` con tipos CREDIT/DEBIT
- Endpoint solo para ADMIN
- Auditoría con `created_by`
- No altera `price_at_purchase` original
- **Generación automática de ClientCredit** para ajustes tipo CREDIT

**❌ Faltante:**
- **Validación de montos**: No hay validación de que el ajuste sea razonable

**Recomendaciones:**
1. Agregar validaciones de montos razonables
2. Considerar flujo de aprobación para ajustes grandes

---

## 4.6 Marketplace de Productos

### Calificación General: **8/10**

#### RFD-MKT-01 — Catálogo e inventario ⭐ **8.5/10**

**✅ Implementado:**
- CRUD completo de productos
- Modelo `ProductVariant` con stock
- Validación de stock al agregar al carrito
- **Modelo `InventoryMovement`** para auditoría
- **Disminución automática al confirmar pago** (en `OrderService.transition_to`)

**❌ Faltante:**
- **Reservas de stock al checkout**: No se reserva stock al crear orden, solo al confirmar pago

**Recomendaciones:**
1. Implementar reserva de stock al checkout
2. Considerar agregar expiración de reservas

---

#### RFD-MKT-02 — Variantes/SKUs ⭐ **9.5/10**

**✅ Implementado:**
- Modelo `ProductVariant` con SKU único
- Soporte para tallas/fragancias
- Validación de SKU único (`unique=True`)
- Checkout calcula stock por SKU

**❌ Faltante:**
- Ninguno significativo

**Recomendaciones:**
1. Mejorar mensajes de error para SKU duplicado

---

#### RFD-MKT-03 — Carrito y checkout ⭐ **8.5/10**

**✅ Implementado:**
- Carrito persistente (`Cart` y `CartItem`)
- Cálculo de totales VIP/CLIENT
- Endpoint de checkout
- Creación de Order
- **Idempotencia al crear Order** (`@idempotent_view`)

**❌ Faltante:**
- **Re-cálculo de precios al pagar**: No se re-calculan precios al momento del pago

**Recomendaciones:**
1. Re-calcular precios al momento del pago en webhook
2. Considerar agregar validación de stock al pagar

---

#### RFD-MKT-04 — Entregas y estados ⭐ **8/10**

**✅ Implementado:**
- Estados: PENDING_PAYMENT, PAID, PREPARING, SHIPPED, DELIVERED
- Asociación opcional a Appointment
- Campos de tracking y shipping

**❌ Faltante:**
- **Notificación de cambio de estado**: No hay notificaciones automáticas
- **Transiciones de estado validadas**: No hay validación explícita

**Recomendaciones:**
1. Implementar notificaciones automáticas de cambio de estado
2. Agregar validación de transiciones de estado en `OrderService`

---

#### RFD-MKT-05 — Devoluciones (RMA) ⭐ **7.5/10**

**✅ Implementado:**
- Estados: RETURN_REQUESTED, RETURN_APPROVED, RETURN_REJECTED, REFUNDED
- Endpoint para solicitar devolución
- Endpoint para procesar devolución (ADMIN)
- Modelo con `return_reason` y `return_request_data`

**❌ Faltante:**
- **Políticas por tipo de producto**: No hay configuración de políticas de devolución
- **Generación automática de ClientCredit o reembolso**: No se genera automáticamente al aprobar
- **Validación de tiempos**: No se valida que la devolución esté dentro del plazo permitido

**Recomendaciones:**
1. Crear modelo de políticas de devolución por tipo de producto
2. Implementar generación automática de crédito/reembolso
3. Validar tiempos de devolución según `return_window_days` en GlobalSettings

---

## 4.7 Contenido y Notificaciones

### Calificación General: **8.5/10**

#### RFD-NOT-01 — Preferencias de notificación por usuario ⭐ **9/10**

**✅ Implementado:**
- **Modelo `NotificationPreference`** con campos para cada canal
- **Canales**: Email/SMS/Push configurados
- **Ventanas de silencio** (`quiet_hours_start`, `quiet_hours_end`)
- **Opt-out por tipo** (canales individuales)
- **Fallback a canal alterno** (implementado en `NotificationService`)
- Endpoints para gestionar preferencias (implícitos en sistema)

**❌ Faltante:**
- **Opt-out por tipo de mensaje**: No hay configuración granular por tipo de evento

**Recomendaciones:**
1. Agregar configuración de opt-out por tipo de evento
2. Considerar agregar preferencias por prioridad

---

#### RFD-NOT-02 — Plantillas versionadas ⭐ **9/10**

**✅ Implementado:**
- **Modelo `NotificationTemplate`** con versionado
- **Sistema de variables** (Django Template)
- **Versionado** (`simple_history`)
- **Auditoría de cambios** (vía simple_history)

**❌ Faltante:**
- **Vista previa**: No hay endpoint de preview

**Recomendaciones:**
1. Crear endpoint de preview de plantillas
2. Considerar agregar editor visual de plantillas

---

#### RFD-NOT-03 — Eventos principales (catálogo) ⭐ **7.5/10**

**✅ Implementado:**
- **Recordatorio de cita (24h)** (`send_appointment_reminder` task)
- **Recordatorio 2h antes** (`check_upcoming_appointments_2h` task)
- **Notificación de lista de espera** (`notify_waitlist_availability` task)
- **Orquestación vía cola** (Celery tasks)
- **Retries ante fallas** (autoretry_for en tasks)
- **Métricas de entrega** (`NotificationLog` model)

**❌ Faltante:**
- **Confirmación/cancelación**: Notificaciones básicas pero no sistemáticas
- **Pago aprobado/declinado**: No hay notificaciones específicas
- **Suscripción VIP cambios**: No hay notificaciones
- **Entrega enviada**: No hay notificaciones
- **Canales en tiempo real**: No hay push notifications implementadas

**Recomendaciones:**
1. Implementar todos los eventos faltantes
2. Integrar push notifications (Firebase, OneSignal, etc.)
3. Crear catálogo de eventos documentado

---

## 4.8 Analíticas y Reportes

### Calificación General: **8.5/10**

#### RFD-ANL-01 — KPIs definidos ⭐ **9/10**

**✅ Implementado:**
- **KPIs específicos implementados**:
  - Conversión a cita (`_get_conversion_rate`)
  - Tasa de no-show (`_get_no_show_rate`)
  - % de reagendos (`_get_reschedule_rate`)
  - LTV VIP vs CLIENT (`_get_ltv_by_role`)
  - Utilización de cabinas/STAFF (`_get_utilization_rate`)
  - AOV (carrito) (`_get_average_order_value`)
- **Consistencia de zona horaria** (America/Bogota)
- **Exportación CSV** (`AnalyticsExportView`)
- **Filtros por rango, rol, servicio** (staff_id, service_category_id)

**❌ Faltante:**
- **Recuperación de deuda**: No está implementado
- **Exportación XLSX**: Solo CSV
- **Definiciones y fórmulas documentadas**: No hay documentación

**Recomendaciones:**
1. Implementar KPI de recuperación de deuda
2. Agregar exportación a XLSX
3. Documentar definiciones y fórmulas

---

#### RFD-ANL-02 — Cuadros operativos ⭐ **9/10**

**✅ Implementado:**
- **Agenda del día** (`agenda_today` endpoint)
- **Cobros pendientes** (`pending_payments` endpoint)
- **Créditos por vencer** (`expiring_credits` endpoint)
- **Suscripciones por renovar** (`renewals` endpoint)
- **Indicadores accionables** (links a detalle en payload)

**❌ Faltante:**
- **Actualización casi en tiempo real**: No hay WebSockets o polling

**Recomendaciones:**
1. Implementar actualización en tiempo real (WebSockets o polling)
2. Considerar agregar más cuadros operativos

---

## 4.9 Chatbot y Asistente Virtual

### Calificación General: **7/10**

#### RFD-BOT-01 — Guardrails y permisos ⭐ **7.5/10**

**✅ Implementado:**
- Endpoint de bot con autenticación
- Throttling (`BotRateThrottle`)
- Integración con Gemini

**❌ Faltante:**
- **Respeto de roles**: No se evidencia validación explícita de roles en respuestas
- **No expone PII a no autenticados**: El endpoint requiere autenticación pero podría mejorarse
- **Rate-limit por IP/usuario**: Solo hay throttling básico
- **Máx. turnos por conversación**: No implementado
- **Verificación adicional para citas/órdenes**: No implementado

**Recomendaciones:**
1. Implementar validación explícita de roles en respuestas del bot
2. Mejorar rate-limiting por IP y usuario
3. Implementar límite de turnos por conversación
4. Agregar verificación adicional para acciones críticas

---

#### RFD-BOT-02 — Flujos principales ⭐ **6.5/10**

**✅ Implementado:**
- Estructura básica con Gemini
- Endpoints de preview y ejecución de acciones
- **Flujos específicos implementados**:
  - Consultar disponibilidad (`_check_availability`)
  - Agendar (`_book_appointment`)
  - Cancelar (`_cancel_appointment`)
- **Confirmación antes de ejecutar** (preview endpoint)

**❌ Faltante:**
- **Reagendar**: No implementado
- **Políticas**: No implementado
- **Precios**: No implementado
- **Estado de pedido**: No implementado
- **Registro de interacciones**: No hay modelo para auditoría

**Recomendaciones:**
1. Implementar todos los flujos requeridos
2. Crear modelo `BotInteraction` para auditoría
3. Mejorar integración con Gemini para respuestas más naturales

---

## 4.10 Configuración Global

### Calificación General: **9/10**

#### RFD-CFG-01 — GlobalSettings ⭐ **9/10**

**✅ Implementado:**
- Modelo `GlobalSettings` como singleton
- Campos: `advance_payment_percentage`, `advance_expiration_minutes`, `appointment_buffer_time`, `low_supervision_capacity`, `vip_monthly_price`, `credit_expiration_days`, `no_show_credit_policy`, `loyalty_months_required`, `loyalty_voucher_service`, `return_window_days`
- Caché para lecturas rápidas
- Solo ADMIN puede modificar (implícito)
- **Auditoría de cambios** (vía simple_history si está configurado)

**❌ Faltante:**
- **`quiet_hours`**: No implementado (está en NotificationPreference)
- **`timezone_display`**: No implementado (está en settings)
- **`waitlist_enabled`**: No implementado

**Recomendaciones:**
1. Agregar campos faltantes si son necesarios
2. Crear endpoint/admin para gestionar configuración
3. Considerar agregar historial de cambios en AuditLog

---

## Resumen de Calificaciones por Módulo

| Módulo | Calificación | Estado |
|--------|--------------|--------|
| 4.1 Autenticación y Gestión de Usuarios | **8/10** | 🟢 Muy bueno |
| 4.2 Perfil Clínico del Cliente | **8.5/10** | 🟢 Muy bueno |
| 4.3 Servicios y Horarios | **9/10** | 🟢 Excelente |
| 4.4 Citas (Agenda) | **8.5/10** | 🟢 Muy bueno |
| 4.5 Pagos, Paquetes y VIP | **8/10** | 🟢 Muy bueno |
| 4.6 Marketplace de Productos | **8/10** | 🟢 Muy bueno |
| 4.7 Contenido y Notificaciones | **8.5/10** | 🟢 Muy bueno |
| 4.8 Analíticas y Reportes | **8.5/10** | 🟢 Muy bueno |
| 4.9 Chatbot y Asistente Virtual | **7/10** | 🟡 Bueno, mejoras necesarias |
| 4.10 Configuración Global | **9/10** | 🟢 Excelente |

**Calificación General del Sistema: 8.3/10**

---

## Prioridades de Implementación

### 🔴 Crítico (Implementar inmediatamente)
1. **Integración real de cobros recurrentes VIP** (RFD-VIP-01) - Integrar con Wompi subscriptions
2. **Notificaciones de eventos faltantes** (RFD-NOT-03) - Pago aprobado/declinado, VIP cambios, entregas
3. **Push notifications** (RFD-NOT-03) - Integrar Firebase/OneSignal
4. **Reserva de stock en marketplace** (RFD-MKT-01) - Al checkout

### 🟠 Alto (Implementar en corto plazo)
1. **Flujos faltantes del chatbot** (RFD-BOT-02) - Reagendar, políticas, precios, estado de pedido
2. **Políticas de devolución** (RFD-MKT-05) - Configuración y validación de tiempos
3. **Generación automática de crédito/reembolso en devoluciones** (RFD-MKT-05)
4. **KPI de recuperación de deuda** (RFD-ANL-01)
5. **Exportación XLSX** (RFD-ANL-01)

### 🟡 Medio (Implementar en mediano plazo)
1. **Enmascaramiento de datos sensibles** (RFD-AUTH-03)
2. **Bloqueo de registro CNG** (RFD-AUTH-04)
3. **Modo quiosco completo** (RFD-CLI-02) - Middleware y pantalla segura
4. **Re-cálculo de precios al pagar** (RFD-MKT-03)
5. **Notificaciones de cambio de estado de órdenes** (RFD-MKT-04)
6. **Registro de interacciones del bot** (RFD-BOT-02)

### 🟢 Bajo (Mejoras y optimizaciones)
1. **Mejoras en mensajes de error con códigos específicos**
2. **Optimización de recomendaciones de terapeutas**
3. **Mejoras en iCal export**
4. **Validaciones adicionales**
5. **Documentación de APIs (OpenAPI/Swagger)**
6. **Tests de autorización**

---

## Observaciones Generales

### Fortalezas
- ✅ Arquitectura sólida con separación de responsabilidades
- ✅ Uso adecuado de Django REST Framework
- ✅ Integración con servicios externos (Twilio, Wompi)
- ✅ Sistema de auditoría implementado
- ✅ Uso de Celery para tareas asíncronas
- ✅ Modelos bien diseñados con relaciones apropiadas
- ✅ Sistema de idempotencia implementado
- ✅ Sistema de notificaciones bien estructurado
- ✅ KPIs y reportes implementados
- ✅ Configuración global centralizada

### Debilidades
- ❌ Cobros recurrentes VIP no integrados completamente con pasarela
- ❌ Algunos eventos de notificación faltantes
- ❌ Push notifications no implementadas
- ❌ Chatbot con funcionalidad limitada
- ❌ Falta de documentación de APIs (OpenAPI/Swagger)
- ❌ Algunos códigos de error no estandarizados

### Recomendaciones Estratégicas
1. **Completar integración de cobros recurrentes**: Es crítico para el modelo de negocio VIP
2. **Implementar push notifications**: Mejora significativa en experiencia de usuario
3. **Completar flujos del chatbot**: Aumenta valor del asistente virtual
4. **Mejorar documentación**: OpenAPI/Swagger para facilitar integración
5. **Aumentar cobertura de tests**: Especialmente para lógica de negocio crítica
6. **Estandarizar códigos de error**: Según catálogo del RFD

---

**Fin del Documento de Evaluación**
