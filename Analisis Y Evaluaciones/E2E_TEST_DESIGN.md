# 🧪 DISEÑO DE PRUEBAS END-TO-END (E2E) - ZENZSPA

## 📋 CONVENCIONES

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

# 🟢 MÓDULO: AUTENTICACIÓN Y USUARIOS

## AUTH-001: Registro de Usuario Nuevo (Happy Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono válido (+573001234567)
📱 Ingresar nombre "Juan"
📱 Ingresar apellido "Pérez"
📱 Ingresar email válido "juan@test.com"
📱 Ingresar contraseña válida "Test123!@#"
📱 Confirmar contraseña
➡️ Click en "Registrarse"
✅ Verificar redirección a /verify-otp
✅ Verificar que se muestra mensaje "Código enviado"
🔔 Verificar SMS recibido (mock Twilio)
📱 Ingresar código OTP válido
➡️ Click en "Verificar"
✅ Verificar redirección a /dashboard
✅ Verificar tokens JWT en localStorage
✅ Verificar usuario en estado is_verified=True
💾 Verificar ClinicalProfile creado automáticamente
💾 Verificar NotificationPreference creado
```

## AUTH-002: Registro con Teléfono Existente (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono ya registrado
📱 Completar resto del formulario válido
➡️ Click en "Registrarse"
✅ Verificar error "Un usuario con este número de teléfono ya existe"
✅ Verificar que NO se envía SMS
✅ Verificar permanencia en /register
```

## AUTH-003: Registro con Teléfono Bloqueado/CNG (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar teléfono en BlockedPhoneNumber
📱 Completar resto del formulario
➡️ Click en "Registrarse"
✅ Verificar error "Este número de teléfono está bloqueado"
💾 Verificar task send_non_grata_alert_to_admins ejecutada
🔔 Verificar notificación a admins
```

## AUTH-004: Registro con Contraseña Débil (Sad Path)
```
➡️ Navegar a /register
📱 Ingresar datos válidos
📱 Ingresar contraseña "123456"
➡️ Click en "Registrarse"
✅ Verificar error "Debe tener al menos 8 caracteres"
✅ Verificar error "Debe incluir al menos una letra mayúscula"
✅ Verificar error "Debe incluir al menos un símbolo"
```

## AUTH-005: Verificación OTP Expirado (Sad Path)
```
➡️ Completar registro exitoso
✅ Llegar a pantalla /verify-otp
⏱️ Esperar 10 minutos (o simular expiración)
📱 Ingresar código OTP
➡️ Click en "Verificar"
✅ Verificar error "El código de verificación es inválido o ha expirado"
✅ Verificar botón "Reenviar código" visible
```

## AUTH-006: Verificación OTP con Intentos Agotados (Sad Path)
```
➡️ Llegar a pantalla /verify-otp
📱 Ingresar código incorrecto
➡️ Click en "Verificar"
✅ Verificar error "Código inválido"
📱 Repetir 2 veces más (3 intentos totales)
✅ Verificar mensaje "Demasiados intentos. Inténtalo en X minutos"
✅ Verificar formulario deshabilitado
⏱️ Esperar período de lockout
✅ Verificar formulario habilitado nuevamente
```

## AUTH-007: Verificación OTP Requiere reCAPTCHA (Sad Path)
```
➡️ Generar múltiples intentos OTP desde misma IP
📱 Ingresar código en intento N+1
➡️ Click en "Verificar"
✅ Verificar que aparece reCAPTCHA
✅ Verificar error si no se completa reCAPTCHA
📱 Completar reCAPTCHA
📱 Ingresar código correcto
➡️ Click en "Verificar"
✅ Verificar login exitoso
```

## AUTH-008: Login con Credenciales Válidas (Happy Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono registrado y verificado
📱 Ingresar contraseña correcta
➡️ Click en "Iniciar Sesión"
✅ Verificar redirección a /dashboard
✅ Verificar access_token en localStorage
✅ Verificar refresh_token en localStorage
💾 Verificar UserSession creada
💾 Verificar last_login actualizado
```

## AUTH-009: Login con Usuario No Verificado (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono no verificado
📱 Ingresar contraseña correcta
➡️ Click en "Iniciar Sesión"
✅ Verificar error "El número de teléfono no ha sido verificado"
✅ Verificar botón "Reenviar verificación" visible
```

## AUTH-010: Login con Usuario CNG/Bloqueado (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono de usuario is_persona_non_grata=True
📱 Ingresar contraseña
➡️ Click en "Iniciar Sesión"
✅ Verificar error genérico (no revelar que está bloqueado)
✅ Verificar NO se genera token
```

## AUTH-011: Login con Múltiples Intentos Fallidos (Sad Path)
```
➡️ Navegar a /login
📱 Ingresar teléfono válido
📱 Ingresar contraseña incorrecta 5 veces
✅ Verificar que aparece reCAPTCHA en intento 6
📱 No completar reCAPTCHA
➡️ Click en "Iniciar Sesión"
✅ Verificar error "Completa reCAPTCHA para continuar"
```

## AUTH-012: Refresh Token (Happy Path)
```
➡️ Login exitoso
✅ Obtener access_token y refresh_token
⏱️ Esperar expiración de access_token (15 min)
➡️ Hacer request a endpoint protegido
✅ Verificar que se hace refresh automático
✅ Verificar nuevo access_token
💾 Verificar UserSession.refresh_token_jti actualizado
```

## AUTH-013: Refresh Token Revocado (Sad Path)
```
➡️ Login exitoso en Dispositivo A
➡️ Login exitoso en Dispositivo B
➡️ En Dispositivo B: Cerrar todas las sesiones
➡️ En Dispositivo A: Intentar refresh
✅ Verificar error "Token inválido o revocado"
✅ Verificar redirección a /login
```

## AUTH-014: Logout Individual (Happy Path)
```
➡️ Login exitoso
➡️ Click en "Cerrar Sesión"
✅ Verificar tokens eliminados de localStorage
✅ Verificar redirección a /login
💾 Verificar refresh_token en BlacklistedToken
💾 Verificar UserSession.is_active=False
➡️ Intentar acceder a /dashboard
✅ Verificar redirección a /login
```

## AUTH-015: Logout de Todas las Sesiones (Happy Path)
```
➡️ Login en múltiples dispositivos (3 sesiones)
➡️ En dispositivo principal: Click "Cerrar todas las sesiones"
✅ Verificar logout en dispositivo actual
💾 Verificar todas las UserSession.is_active=False
💾 Verificar todos los tokens en BlacklistedToken
➡️ En otros dispositivos: Verificar sesión expirada
```

## AUTH-016: Recuperación de Contraseña (Happy Path)
```
➡️ Navegar a /forgot-password
📱 Ingresar teléfono registrado
➡️ Click en "Enviar Código"
✅ Verificar mensaje "Si existe una cuenta..."
🔔 Verificar SMS recibido
➡️ Navegar a /reset-password
📱 Ingresar código OTP
📱 Ingresar nueva contraseña válida
📱 Confirmar nueva contraseña
➡️ Click en "Restablecer"
✅ Verificar mensaje "Contraseña actualizada"
💾 Verificar todas las sesiones revocadas
➡️ Login con nueva contraseña
✅ Verificar login exitoso
```

## AUTH-017: Recuperación de Contraseña - Teléfono Inexistente (Sad Path)
```
➡️ Navegar a /forgot-password
📱 Ingresar teléfono no registrado
➡️ Click en "Enviar Código"
✅ Verificar mismo mensaje "Si existe una cuenta..." (no revelar)
✅ Verificar que NO se envía SMS
```

## AUTH-018: Cambio de Contraseña Autenticado (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
📱 Ingresar contraseña actual
📱 Ingresar nueva contraseña válida
📱 Confirmar nueva contraseña
➡️ Click en "Cambiar Contraseña"
✅ Verificar mensaje "Contraseña actualizada"
✅ Verificar logout automático
💾 Verificar todas las sesiones revocadas
➡️ Login con nueva contraseña
✅ Verificar login exitoso
```

## AUTH-019: Cambio de Contraseña - Contraseña Actual Incorrecta (Sad Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
📱 Ingresar contraseña actual incorrecta
📱 Ingresar nueva contraseña válida
➡️ Click en "Cambiar Contraseña"
✅ Verificar error "La contraseña actual es incorrecta"
✅ Verificar sesión NO cerrada
```

## AUTH-020: Gestión de Sesiones Activas (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/sessions
✅ Verificar lista de sesiones activas
✅ Verificar IP, User Agent, última actividad por sesión
➡️ Click en "Cerrar" en sesión específica
✅ Verificar sesión removida de lista
💾 Verificar UserSession.is_active=False
💾 Verificar token en BlacklistedToken
```

## AUTH-021: Configuración 2FA TOTP (Happy Path)
```
➡️ Login exitoso
➡️ Navegar a /settings/security
➡️ Click en "Activar 2FA"
✅ Verificar código QR mostrado
✅ Verificar secret key mostrado
📱 Escanear QR con app autenticadora
📱 Ingresar código de 6 dígitos
➡️ Click en "Verificar"
✅ Verificar mensaje "2FA activado correctamente"
💾 Verificar user.totp_secret guardado
```

## AUTH-022: Login con 2FA Activo (Happy Path)
```
➡️ Navegar a /login (usuario con 2FA)
📱 Ingresar credenciales
➡️ Click en "Iniciar Sesión"
✅ Verificar redirección a /verify-2fa
📱 Ingresar código TOTP actual
➡️ Click en "Verificar"
✅ Verificar login exitoso
✅ Verificar redirección a /dashboard
```

## AUTH-023: Login con 2FA - Código Incorrecto (Sad Path)
```
➡️ Navegar a /login (usuario con 2FA)
📱 Ingresar credenciales
➡️ Click en "Iniciar Sesión"
📱 Ingresar código TOTP incorrecto
➡️ Click en "Verificar"
✅ Verificar error "Código inválido"
✅ Verificar permanencia en /verify-2fa
```

---

# 🟢 MÓDULO: PERFIL CLÍNICO

## PROFILE-001: Ver Perfil Propio (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile
✅ Verificar datos personales mostrados
✅ Verificar dosha actual
✅ Verificar nivel de actividad
✅ Verificar lista de dolores localizados
✅ Verificar consentimientos firmados
```

## PROFILE-002: Actualizar Perfil Clínico (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile/edit
📱 Modificar tipo de dieta a "VEGAN"
📱 Modificar calidad de sueño a "POOR"
📱 Agregar condición médica "Diabetes Tipo 2"
➡️ Click en "Guardar"
✅ Verificar mensaje "Perfil actualizado"
💾 Verificar campos encriptados en BD
💾 Verificar entrada en historial (simple_history)
```

## PROFILE-003: Agregar Dolor Localizado (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile/pains
➡️ Click en "Agregar Dolor"
📱 Seleccionar parte del cuerpo "Espalda Baja"
📱 Seleccionar nivel "MODERATE"
📱 Seleccionar periodicidad "OCCASIONAL"
📱 Agregar notas "Empeora al estar sentado"
➡️ Click en "Guardar"
✅ Verificar dolor agregado a lista
💾 Verificar LocalizedPain creado
```

## PROFILE-004: Completar Cuestionario Dosha (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile/dosha-quiz
✅ Verificar todas las preguntas cargadas
📱 Responder cada pregunta seleccionando opción
➡️ Click en "Enviar Respuestas"
✅ Verificar resultado mostrado (ej: "VATA")
✅ Verificar elemento asociado mostrado
💾 Verificar ClientDoshaAnswer creadas
💾 Verificar ClinicalProfile.dosha actualizado
```

## PROFILE-005: Cuestionario Dosha Incompleto (Sad Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile/dosha-quiz
📱 Responder solo 5 de 10 preguntas
➡️ Click en "Enviar Respuestas"
✅ Verificar error "Debes responder todas las preguntas"
✅ Verificar contador "Respondidas: 5/10"
```

## PROFILE-006: Firmar Consentimiento (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /profile/consents
✅ Verificar template de consentimiento activo
✅ Verificar texto legal completo
📱 Scroll hasta el final
📱 Marcar checkbox "He leído y acepto"
➡️ Click en "Firmar Consentimiento"
✅ Verificar mensaje "Consentimiento firmado"
💾 Verificar ConsentDocument creado
💾 Verificar signature_hash generado
💾 Verificar IP capturada
```

## PROFILE-007: Consentimiento Ya Firmado (Sad Path)
```
➡️ Login como CLIENT con consentimiento v1 firmado
➡️ Navegar a /profile/consents
➡️ Intentar firmar misma versión
✅ Verificar error "Ya existe un consentimiento firmado para esta versión"
✅ Verificar fecha de firma anterior mostrada
```

## PROFILE-008: Exportar Datos Personales GDPR (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /settings/privacy
➡️ Click en "Exportar Mis Datos"
✅ Verificar descarga de archivo JSON
✅ Verificar contenido incluye: perfil, dolores, consentimientos, respuestas dosha
💾 Verificar AuditLog de exportación creado
```

## PROFILE-009: Modo Kiosk - Inicio de Sesión por Staff (Happy Path)
```
➡️ Login como STAFF
➡️ Navegar a /kiosk/start
📱 Ingresar teléfono del cliente
➡️ Click en "Iniciar Sesión Kiosk"
✅ Verificar token generado
✅ Verificar tiempo de expiración mostrado (5 min)
💾 Verificar KioskSession creada
➡️ Entregar dispositivo al cliente
```

## PROFILE-010: Modo Kiosk - Cliente Completa Cuestionario (Happy Path)
```
➡️ Continuar desde PROFILE-009
✅ Verificar pantalla de kiosk con timer
📱 Cliente responde cuestionario dosha
➡️ Click en "Enviar"
✅ Verificar resultado mostrado
💾 Verificar KioskSession.status=COMPLETED
✅ Verificar pantalla de "Gracias" mostrada
```

## PROFILE-011: Modo Kiosk - Sesión Expirada (Sad Path)
```
➡️ Continuar desde PROFILE-009
⏱️ Esperar 5 minutos sin actividad
✅ Verificar pantalla segura mostrada automáticamente
✅ Verificar mensaje "Sesión expirada"
💾 Verificar KioskSession.status=LOCKED
➡️ Intentar hacer submit
✅ Verificar error 440 (Login Timeout)
```

## PROFILE-012: Modo Kiosk - Heartbeat (Happy Path)
```
➡️ Continuar desde PROFILE-009
✅ Verificar heartbeat enviado cada 30 segundos
✅ Verificar timer reiniciado
💾 Verificar KioskSession.last_activity actualizado
```

## PROFILE-013: Modo Kiosk - Cambios Pendientes y Bloqueo (Sad Path)
```
➡️ Cliente en kiosk modifica perfil parcialmente
➡️ Staff presiona "Bloquear Sesión" remotamente
✅ Verificar pantalla segura mostrada
✅ Verificar popup "¿Descartar cambios?"
➡️ Click en "Descartar"
✅ Verificar cambios NO guardados
💾 Verificar KioskSession.has_pending_changes=False
```

---

# 🟢 MÓDULO: SERVICIOS Y CITAS

## APPT-001: Ver Catálogo de Servicios (Happy Path)
```
➡️ Navegar a /services (público o autenticado)
✅ Verificar lista de servicios activos
✅ Verificar nombre, duración, precio por servicio
✅ Verificar categorías agrupadas
✅ Verificar servicios inactivos NO mostrados
```

## APPT-002: Ver Disponibilidad para Servicio (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /book
📱 Seleccionar servicio "Masaje Relajante"
📱 Seleccionar fecha futura
➡️ Click en "Ver Disponibilidad"
✅ Verificar slots disponibles mostrados
✅ Verificar nombre del staff por slot
✅ Verificar buffer time aplicado (slots no contiguos)
```

## APPT-003: Ver Disponibilidad - Sin Slots (Sad Path)
```
➡️ Login como CLIENT
➡️ Navegar a /book
📱 Seleccionar servicio
📱 Seleccionar fecha con todos los slots ocupados
➡️ Click en "Ver Disponibilidad"
✅ Verificar mensaje "No hay disponibilidad para esta fecha"
✅ Verificar sugerencia de otras fechas
```

## APPT-004: Crear Cita - Flujo Completo (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /book
📱 Seleccionar servicio(s)
📱 Seleccionar fecha y hora disponible
📱 Seleccionar staff (opcional)
➡️ Click en "Continuar"
✅ Verificar resumen de cita
✅ Verificar precio total
✅ Verificar monto de anticipo (20%)
➡️ Click en "Confirmar y Pagar"
✅ Verificar redirección a pasarela Wompi
💾 Verificar Appointment creada en PENDING_PAYMENT
💾 Verificar Payment creada en PENDING
```

## APPT-005: Crear Cita - Pago Exitoso vía Webhook (Happy Path)
```
➡️ Continuar desde APPT-004
➡️ Completar pago en Wompi (sandbox aprobado)
🔄 Webhook recibido con status APPROVED
💾 Verificar Payment.status=APPROVED
💾 Verificar Appointment.status=CONFIRMED
🔔 Verificar notificación WhatsApp/Email enviada
✅ Verificar redirección a /appointments/confirmation
```

## APPT-006: Crear Cita - Pago Fallido (Sad Path)
```
➡️ Continuar desde APPT-004
➡️ Pago rechazado en Wompi
🔄 Webhook recibido con status DECLINED
💾 Verificar Payment.status=DECLINED
💾 Verificar Appointment.status=PENDING_PAYMENT (sin cambio)
🔔 Verificar notificación de fallo enviada
✅ Verificar opción de reintentar pago
```

## APPT-007: Crear Cita - Timeout de Pago (Sad Path)
```
➡️ Continuar desde APPT-004
⏱️ Esperar 20 minutos sin pagar
🔄 Task cancel_unpaid_appointments ejecutada
💾 Verificar Appointment.status=CANCELLED
💾 Verificar Appointment.outcome=CANCELLED_BY_SYSTEM
💾 Verificar AuditLog creado
🔔 Verificar notificación de cancelación enviada
```

## APPT-008: Crear Cita con Crédito a Favor (Happy Path)
```
➡️ Login como CLIENT con ClientCredit disponible
➡️ Navegar a /book
📱 Seleccionar servicio con anticipo $20,000
✅ Verificar crédito disponible mostrado ($25,000)
📱 Opción "Usar crédito" seleccionada
➡️ Click en "Confirmar"
💾 Verificar Payment.status=PAID_WITH_CREDIT
💾 Verificar ClientCredit.remaining_amount reducido
💾 Verificar Appointment.status=CONFIRMED
✅ Verificar NO redirección a Wompi
```

## APPT-009: Crear Cita con Crédito Parcial (Happy Path)
```
➡️ Login como CLIENT con ClientCredit $10,000
➡️ Crear cita con anticipo $20,000
✅ Verificar "Crédito aplicado: $10,000"
✅ Verificar "A pagar: $10,000"
➡️ Completar pago de diferencia en Wompi
💾 Verificar PaymentCreditUsage creado
💾 Verificar ClientCredit agotado
```

## APPT-010: Crear Cita - Límite de Citas Activas CLIENT (Sad Path)
```
➡️ Login como CLIENT con 1 cita confirmada
➡️ Intentar crear segunda cita
✅ Verificar error "Límite de citas activas excedido"
✅ Verificar sugerencia de upgrade a VIP
```

## APPT-011: Crear Cita - Límite de Citas Activas VIP (Happy Path)
```
➡️ Login como VIP con 3 citas confirmadas
➡️ Intentar crear cuarta cita
✅ Verificar cita creada exitosamente (límite VIP = 4)
➡️ Intentar crear quinta cita
✅ Verificar error "Límite de citas activas excedido"
```

## APPT-012: Crear Cita - Usuario con Deuda Pendiente (Sad Path)
```
➡️ Login como CLIENT con Payment FINAL pendiente
➡️ Intentar crear nueva cita
✅ Verificar error "Usuario bloqueado por deuda pendiente"
✅ Verificar enlace a pagar deuda
```

## APPT-013: Crear Cita - Conflicto de Horario (Sad Path)
```
➡️ Login como CLIENT
➡️ Otro usuario reserva slot 10:00
➡️ Cliente intenta reservar mismo slot 10:00
✅ Verificar error "Horario no disponible por solapamiento"
✅ Verificar actualización de slots disponibles
```

## APPT-014: Reagendar Cita - Dentro de Política (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /appointments/[id]
➡️ Click en "Reagendar"
📱 Seleccionar nueva fecha/hora (>24h antes)
➡️ Click en "Confirmar Reagendamiento"
✅ Verificar mensaje "Cita reagendada"
💾 Verificar Appointment.reschedule_count incrementado
💾 Verificar Appointment.status=RESCHEDULED
🔔 Verificar notificación enviada
```

## APPT-015: Reagendar Cita - Menos de 24h (Sad Path)
```
➡️ Login como CLIENT
➡️ Cita programada para dentro de 20 horas
➡️ Intentar reagendar
✅ Verificar error "Solo puedes reagendar con más de 24 horas de anticipación"
```

## APPT-016: Reagendar Cita - Límite de Reagendamientos (Sad Path)
```
➡️ Login como CLIENT
➡️ Cita con reschedule_count=2
➡️ Intentar reagendar tercera vez
✅ Verificar error "Has alcanzado el límite de reagendamientos"
```

## APPT-017: Reagendar Cita - Staff Override (Happy Path)
```
➡️ Login como STAFF
➡️ Navegar a /admin/appointments/[id]
➡️ Cita del cliente con reschedule_count=2
➡️ Click en "Forzar Reagendamiento"
📱 Seleccionar nueva fecha
➡️ Click en "Confirmar"
✅ Verificar cita reagendada
💾 Verificar AuditLog con APPOINTMENT_RESCHEDULE_FORCE
```

## APPT-018: Cancelar Cita por Cliente (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /appointments/[id]
➡️ Click en "Cancelar Cita"
✅ Verificar popup de confirmación
➡️ Click en "Confirmar Cancelación"
💾 Verificar Appointment.status=CANCELLED
💾 Verificar Appointment.outcome=CANCELLED_BY_CLIENT
🔔 Verificar oferta a waitlist enviada
```

## APPT-019: Completar Cita - Pago Final (Happy Path)
```
➡️ Login como STAFF
➡️ Cliente llega a cita confirmada
➡️ Navegar a /admin/appointments/[id]
➡️ Click en "Registrar Pago Final"
✅ Verificar monto pendiente calculado
📱 Confirmar pago recibido
➡️ Click en "Completar Cita"
💾 Verificar Payment tipo FINAL creado
💾 Verificar Appointment.status=COMPLETED
💾 Verificar cancellation_streak reseteado
🔔 Verificar solicitud de feedback enviada
```

## APPT-020: Marcar No-Show (Sad Path)
```
➡️ Login como STAFF
➡️ Cliente no llega a cita
➡️ Navegar a /admin/appointments/[id]
➡️ Click en "Marcar No-Show"
✅ Verificar popup de confirmación
➡️ Click en "Confirmar"
💾 Verificar Appointment.status=CANCELLED
💾 Verificar Appointment.outcome=NO_SHOW
💾 Verificar política de crédito aplicada (NONE/PARTIAL/FULL)
🔔 Verificar notificación enviada
```

## APPT-021: Servicios de Baja Supervisión - Capacidad (Happy Path)
```
➡️ Login como CLIENT
➡️ Seleccionar servicio de categoría is_low_supervision=True
📱 Seleccionar horario sin staff asignado
✅ Verificar capacidad disponible mostrada
➡️ Confirmar cita
💾 Verificar Appointment.staff_member=NULL
💾 Verificar concurrent_count < low_supervision_capacity
```

## APPT-022: Servicios de Baja Supervisión - Capacidad Agotada (Sad Path)
```
➡️ Capacidad=2, ya hay 2 citas en ese horario
➡️ Login como CLIENT
➡️ Intentar reservar mismo horario
✅ Verificar error "Capacidad máxima alcanzada para este horario"
```

## APPT-023: Lista de Espera - Agregar (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /waitlist
📱 Seleccionar servicios deseados
📱 Seleccionar fecha preferida
📱 Agregar notas opcionales
➡️ Click en "Agregar a Lista de Espera"
✅ Verificar mensaje "Agregado a lista de espera"
💾 Verificar WaitlistEntry creada
```

## APPT-024: Lista de Espera - Oferta Recibida (Happy Path)
```
➡️ Cita cancelada libera slot
🔄 Task ofrece slot a WaitlistEntry
🔔 Verificar notificación enviada al usuario
💾 Verificar WaitlistEntry.status=OFFERED
💾 Verificar offer_expires_at configurado
➡️ Login como CLIENT
✅ Verificar banner "Tienes una oferta de cita"
➡️ Click en "Ver Oferta"
➡️ Click en "Aceptar"
💾 Verificar nueva Appointment creada
💾 Verificar WaitlistEntry.status=CONFIRMED
```

## APPT-025: Lista de Espera - Oferta Expirada (Sad Path)
```
➡️ Continuar desde APPT-024 (oferta enviada)
⏱️ Esperar TTL (60 minutos por defecto)
🔄 Task expira oferta
💾 Verificar WaitlistEntry.status=EXPIRED
🔄 Slot ofrecido al siguiente en lista
```

---

# 🟢 MÓDULO: PAQUETES Y VOUCHERS

## PKG-001: Ver Catálogo de Paquetes (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /packages
✅ Verificar lista de paquetes activos
✅ Verificar servicios incluidos por paquete
✅ Verificar precio y ahorro vs individual
✅ Verificar meses VIP incluidos si aplica
```

## PKG-002: Comprar Paquete (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /packages/[id]
➡️ Click en "Comprar Paquete"
✅ Verificar resumen de compra
➡️ Click en "Pagar"
➡️ Completar pago en Wompi
💾 Verificar UserPackage creado
💾 Verificar Vouchers generados por cada servicio
💾 Verificar expires_at en vouchers
🔔 Verificar notificación con códigos enviada
```

## PKG-003: Ver Mis Vouchers (Happy Path)
```
➡️ Login como CLIENT con vouchers
➡️ Navegar a /vouchers
✅ Verificar lista de vouchers disponibles
✅ Verificar código, servicio, fecha de expiración
✅ Verificar vouchers usados/expirados en sección separada
```

## PKG-004: Usar Voucher en Cita (Happy Path)
```
➡️ Login como CLIENT con voucher para "Masaje Relajante"
➡️ Crear cita para "Masaje Relajante"
✅ Verificar opción "Usar voucher" visible
📱 Ingresar código de voucher
➡️ Click en "Aplicar"
✅ Verificar precio reducido a $0 (o diferencia)
➡️ Confirmar cita
💾 Verificar Voucher.status=USED
💾 Verificar Appointment creada
```

## PKG-005: Usar Voucher - Servicio Incorrecto (Sad Path)
```
➡️ Login como CLIENT con voucher para "Masaje Relajante"
➡️ Crear cita para "Masaje Deportivo"
📱 Intentar usar voucher
✅ Verificar error "Este voucher no aplica para el servicio seleccionado"
```

## PKG-006: Usar Voucher - Expirado (Sad Path)
```
➡️ Login como CLIENT con voucher expirado
➡️ Crear cita para servicio correcto
📱 Intentar usar voucher
✅ Verificar error "Este voucher ha expirado"
```

## PKG-007: Notificación de Voucher por Expirar (Happy Path)
```
🔄 Task notify_expiring_vouchers ejecutada
💾 Vouchers con expires_at = hoy + 3 días
🔔 Verificar notificación enviada a cada propietario
✅ Verificar contenido incluye código, servicio, fecha
```

---

# 🟢 MÓDULO: SUSCRIPCIÓN VIP

## VIP-001: Suscribirse a VIP (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /vip
✅ Verificar beneficios listados
✅ Verificar precio mensual
➡️ Click en "Suscribirme"
➡️ Completar pago en Wompi
💾 Verificar Payment tipo VIP_SUBSCRIPTION
💾 Verificar user.role=VIP
💾 Verificar user.vip_expires_at = hoy + 30 días
💾 Verificar user.vip_active_since = hoy
💾 Verificar SubscriptionLog creado
🔔 Verificar email de bienvenida VIP
```

## VIP-002: Guardar Token para Renovación Automática (Happy Path)
```
➡️ Continuar desde VIP-001
✅ Verificar checkbox "Renovación automática"
📱 Marcar checkbox
💾 Verificar vip_payment_token guardado (payment_source_id)
💾 Verificar vip_auto_renew=True
```

## VIP-003: Renovación Automática Exitosa (Happy Path)
```
➡️ Usuario VIP con vip_expires_at = mañana
🔄 Task process_recurring_subscriptions ejecutada
💾 Verificar cobro exitoso vía token
💾 Verificar Payment tipo VIP_SUBSCRIPTION creado
💾 Verificar vip_expires_at extendido 30 días
💾 Verificar vip_failed_payments=0
🔔 Verificar notificación de renovación exitosa
```

## VIP-004: Renovación Automática Fallida (Sad Path)
```
➡️ Usuario VIP con vip_expires_at = mañana
➡️ Token de pago inválido/sin fondos
🔄 Task process_recurring_subscriptions ejecutada
💾 Verificar cobro fallido
💾 Verificar vip_failed_payments incrementado
🔔 Verificar notificación de fallo
✅ Verificar usuario sigue siendo VIP (gracia)
```

## VIP-005: Cancelación por 3 Fallos Consecutivos (Sad Path)
```
➡️ Usuario VIP con vip_failed_payments=2
🔄 Tercer intento de cobro fallido
💾 Verificar vip_failed_payments=3
💾 Verificar vip_auto_renew=False
🔔 Verificar notificación de suscripción cancelada
```

## VIP-006: Degradación por Expiración (Sad Path)
```
➡️ Usuario VIP con vip_expires_at = ayer
🔄 Task downgrade_expired_vips ejecutada
💾 Verificar user.role=CLIENT
💾 Verificar user.vip_active_since=NULL
💾 Verificar AuditLog con VIP_DOWNGRADED
🔔 Verificar notificación de expiración
```

## VIP-007: Recompensa por Lealtad (Happy Path)
```
➡️ Usuario VIP continuo por 3 meses
🔄 Task check_vip_loyalty ejecutada
💾 Verificar Voucher de recompensa creado
💾 Verificar LoyaltyRewardLog creado
💾 Verificar AuditLog con LOYALTY_REWARD_ISSUED
🔔 Verificar notificación con código de voucher
```

## VIP-008: Cancelar Renovación Automática (Happy Path)
```
➡️ Login como VIP
➡️ Navegar a /settings/subscription
➡️ Click en "Cancelar Renovación Automática"
✅ Verificar popup de confirmación
➡️ Click en "Confirmar"
💾 Verificar vip_auto_renew=False
✅ Verificar mensaje "Seguirás siendo VIP hasta [fecha]"
```

---

# 🟢 MÓDULO: MARKETPLACE

## MKT-001: Ver Catálogo de Productos (Happy Path)
```
➡️ Navegar a /shop (público o autenticado)
✅ Verificar productos activos mostrados
✅ Verificar imagen, nombre, precio
✅ Verificar variantes disponibles
✅ Verificar stock mostrado o "Agotado"
✅ Verificar productos inactivos NO mostrados
```

## MKT-002: Ver Detalle de Producto (Happy Path)
```
➡️ Navegar a /shop/[product-id]
✅ Verificar galería de imágenes
✅ Verificar descripción completa
✅ Verificar variantes con precios
✅ Verificar selector de cantidad
✅ Verificar precio VIP si usuario es VIP
```

## MKT-003: Agregar al Carrito (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /shop/[product-id]
📱 Seleccionar variante
📱 Seleccionar cantidad: 2
➡️ Click en "Agregar al Carrito"
✅ Verificar mensaje "Agregado al carrito"
✅ Verificar badge de carrito actualizado
💾 Verificar CartItem creado
```

## MKT-004: Agregar al Carrito - Sin Stock (Sad Path)
```
➡️ Login como CLIENT
➡️ Producto con stock=0
➡️ Click en "Agregar al Carrito"
✅ Verificar error "Producto agotado"
✅ Verificar botón deshabilitado
```

## MKT-005: Agregar al Carrito - Excede Stock (Sad Path)
```
➡️ Login como CLIENT
➡️ Producto con stock=3
📱 Seleccionar cantidad: 5
➡️ Click en "Agregar al Carrito"
✅ Verificar error "Solo hay 3 unidades disponibles"
```

## MKT-006: Ver Carrito (Happy Path)
```
➡️ Login como CLIENT con items en carrito
➡️ Navegar a /cart
✅ Verificar lista de items
✅ Verificar precio unitario y subtotal
✅ Verificar cantidad editable
✅ Verificar botón eliminar
✅ Verificar total del carrito
```

## MKT-007: Modificar Cantidad en Carrito (Happy Path)
```
➡️ En /cart
📱 Cambiar cantidad de 2 a 3
✅ Verificar subtotal actualizado
✅ Verificar total actualizado
💾 Verificar CartItem.quantity actualizado
```

## MKT-008: Eliminar Item del Carrito (Happy Path)
```
➡️ En /cart
➡️ Click en "Eliminar" en item
✅ Verificar item removido de lista
✅ Verificar total actualizado
💾 Verificar CartItem eliminado
```

## MKT-009: Checkout - Envío a Domicilio (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /cart con items
➡️ Click en "Proceder al Pago"
📱 Seleccionar "Envío a Domicilio"
📱 Ingresar dirección de envío
➡️ Click en "Continuar"
✅ Verificar resumen de orden
✅ Verificar fecha estimada de entrega
➡️ Click en "Pagar"
➡️ Completar pago en Wompi
💾 Verificar Order creada en PENDING_PAYMENT
💾 Verificar stock reservado (reserved_stock)
💾 Verificar InventoryMovement tipo RESERVATION
💾 Verificar reservation_expires_at
```

## MKT-010: Checkout - Recoger en Local (Happy Path)
```
➡️ En checkout
📱 Seleccionar "Recoger en Local"
➡️ Completar pago
💾 Verificar Order.delivery_option=PICKUP
💾 Verificar estimated_delivery_date más corta
```

## MKT-011: Checkout - Asociar a Cita (Happy Path)
```
➡️ Login como CLIENT con cita confirmada
➡️ En checkout
📱 Seleccionar "Asociar a Cita"
📱 Seleccionar cita de la lista
➡️ Completar pago
💾 Verificar Order.associated_appointment
💾 Verificar estimated_delivery_date = fecha de cita
```

## MKT-012: Pago de Orden Exitoso (Happy Path)
```
➡️ Continuar desde MKT-009
🔄 Webhook Wompi recibido APPROVED
💾 Verificar Order.status=PAID
💾 Verificar stock descontado
💾 Verificar reserved_stock liberado
💾 Verificar InventoryMovement tipo SALE
🔔 Verificar notificación de confirmación
💾 Verificar carrito vaciado
```

## MKT-013: Pago de Orden - Timeout de Reserva (Sad Path)
```
➡️ Orden creada con reservation_expires_at
⏱️ Esperar 30 minutos sin pagar
🔄 Task libera reserva
💾 Verificar reserved_stock restaurado
💾 Verificar InventoryMovement tipo RESERVATION_RELEASE
💾 Verificar Order.status=CANCELLED
🔔 Verificar notificación de cancelación
```

## MKT-014: Pago Tardío - Stock Ya No Disponible (Sad Path)
```
➡️ Orden en PENDING_PAYMENT
⏱️ Reserva expira
➡️ Otro cliente compra ese stock
🔄 Webhook APPROVED llega tarde
💾 Verificar Order.status=FRAUD_ALERT o crédito
💾 Verificar ClientCredit creado por monto pagado
🔔 Verificar notificación explicativa
```

## MKT-015: Transición de Estado - Preparando (Happy Path)
```
➡️ Login como STAFF
➡️ Orden en PAID
➡️ Click en "Iniciar Preparación"
💾 Verificar Order.status=PREPARING
🔔 Verificar notificación al cliente
```

## MKT-016: Transición de Estado - Enviado (Happy Path)
```
➡️ Login como STAFF
➡️ Orden en PREPARING
📱 Ingresar número de tracking
➡️ Click en "Marcar Enviado"
💾 Verificar Order.status=SHIPPED
💾 Verificar Order.tracking_number
💾 Verificar Order.shipping_date
🔔 Verificar notificación con tracking
```

## MKT-017: Transición de Estado - Entregado (Happy Path)
```
➡️ Login como STAFF
➡️ Orden en SHIPPED
➡️ Click en "Confirmar Entrega"
💾 Verificar Order.status=DELIVERED
💾 Verificar Order.delivered_at
🔔 Verificar notificación de entrega
```

## MKT-018: Solicitar Devolución (Happy Path)
```
➡️ Login como CLIENT
➡️ Orden DELIVERED hace 5 días
➡️ Navegar a /orders/[id]
➡️ Click en "Solicitar Devolución"
📱 Seleccionar items a devolver
📱 Seleccionar cantidades
📱 Ingresar motivo
➡️ Click en "Enviar Solicitud"
💾 Verificar Order.status=RETURN_REQUESTED
💾 Verificar return_request_data guardado
🔔 Verificar notificación a admin
```

## MKT-019: Solicitar Devolución - Fuera de Ventana (Sad Path)
```
➡️ Login como CLIENT
➡️ Orden DELIVERED hace 35 días (ventana=30)
➡️ Intentar solicitar devolución
✅ Verificar error "La orden excede la ventana de devoluciones"
```

## MKT-020: Aprobar Devolución (Happy Path)
```
➡️ Login como ADMIN
➡️ Orden en RETURN_REQUESTED
➡️ Click en "Aprobar Devolución"
💾 Verificar Order.status=RETURN_APPROVED
💾 Verificar stock restaurado
💾 Verificar InventoryMovement tipo RETURN
💾 Verificar ClientCredit creado
💾 Verificar AuditLog MARKETPLACE_RETURN
🔔 Verificar notificación al cliente
💾 Verificar Order.status=REFUNDED
```

## MKT-021: Rechazar Devolución (Sad Path)
```
➡️ Login como ADMIN
➡️ Orden en RETURN_REQUESTED
➡️ Click en "Rechazar Devolución"
💾 Verificar Order.status=RETURN_REJECTED
🔔 Verificar notificación al cliente
```

## MKT-022: Alerta de Stock Bajo (Happy Path)
```
➡️ Venta reduce stock a threshold
💾 Verificar stock <= low_stock_threshold
🔔 Verificar alerta enviada a admin
✅ Verificar contenido incluye producto y cantidad
```

## MKT-023: Ver Historial de Órdenes (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /orders
✅ Verificar lista de órdenes
✅ Verificar estado, fecha, total por orden
➡️ Click en orden específica
✅ Verificar detalle completo
✅ Verificar items, cantidades, precios
✅ Verificar tracking si aplica
```

---

# 🟢 MÓDULO: NOTIFICACIONES

## NOTIF-001: Recibir Notificación Email (Happy Path)
```
➡️ Evento dispara notificación (ej: cita confirmada)
💾 Verificar NotificationLog creado
💾 Verificar template renderizado
🔔 Verificar email enviado
💾 Verificar NotificationLog.status=SENT
```

## NOTIF-002: Recibir Notificación WhatsApp (Happy Path)
```
➡️ Evento dispara notificación
💾 Verificar template WhatsApp usado
🔔 Verificar mensaje WhatsApp enviado via Twilio
💾 Verificar NotificationLog.status=SENT
```

## NOTIF-003: Notificación en Quiet Hours (Sad Path -> Delayed)
```
➡️ Usuario con quiet_hours 22:00-08:00
➡️ Evento a las 23:00
💾 Verificar NotificationLog.status=SILENCED
💾 Verificar scheduled_for = 08:01
⏱️ A las 08:01
🔔 Verificar notificación enviada
```

## NOTIF-004: Notificación Crítica Ignora Quiet Hours (Happy Path)
```
➡️ Usuario con quiet_hours activo
➡️ Evento con priority="critical"
🔔 Verificar notificación enviada inmediatamente
💾 Verificar status=SENT (no SILENCED)
```

## NOTIF-005: Fallback de Canal (Happy Path)
```
➡️ Usuario con whatsapp_enabled=False, email_enabled=True
➡️ Evento dispara notificación
💾 Verificar canal usado = EMAIL
🔔 Verificar email enviado
```

## NOTIF-006: Sin Canales Habilitados (Sad Path)
```
➡️ Usuario con todos los canales deshabilitados
➡️ Evento dispara notificación
💾 Verificar NotificationLog.status=FAILED
💾 Verificar error_message="El usuario no tiene canales habilitados"
```

## NOTIF-007: Template No Existe (Sad Path)
```
➡️ Evento con event_code sin template
💾 Verificar NotificationLog.status=FAILED
💾 Verificar error_message="No existe plantilla activa"
```

## NOTIF-008: Configurar Preferencias (Happy Path)
```
➡️ Login como CLIENT
➡️ Navegar a /settings/notifications
📱 Deshabilitar email
📱 Configurar quiet hours 23:00-07:00
📱 Cambiar timezone a "America/Mexico_City"
➡️ Click en "Guardar"
💾 Verificar NotificationPreference actualizado
✅ Verificar mensaje de confirmación
```

---

# 🟢 MÓDULO: BOT CONVERSACIONAL

## BOT-001: Conversación Básica - Usuario Registrado (Happy Path)
```
➡️ Login como CLIENT
➡️ Abrir chat widget
📱 Escribir "Hola, qué servicios ofrecen?"
⏱️ Esperar respuesta
✅ Verificar respuesta incluye lista de servicios
✅ Verificar respuesta es JSON válido internamente
💾 Verificar BotConversationLog creado
💾 Verificar tokens_used registrado
```

## BOT-002: Conversación - Usuario Anónimo (Happy Path)
```
➡️ Sin login
➡️ Abrir chat widget
📱 Escribir "Quiero información de masajes"
⏱️ Esperar respuesta
✅ Verificar respuesta amigable
💾 Verificar AnonymousUser creado
💾 Verificar BotConversationLog con anonymous_user
```

## BOT-003: Memoria de Conversación (Happy Path)
```
➡️ Login como CLIENT
➡️ Escribir "Me llamo Carlos"
⏱️ Esperar respuesta
📱 Escribir "Cuánto cuesta el masaje relajante?"
⏱️ Esperar respuesta
📱 Escribir "Cómo me llamo?"
✅ Verificar respuesta menciona "Carlos"
💾 Verificar historial en cache
```

## BOT-004: Solicitar Handoff Explícito (Happy Path)
```
➡️ Login como CLIENT
📱 Escribir "Quiero hablar con una persona real"
⏱️ Esperar respuesta
✅ Verificar bot pregunta por servicio de interés
📱 Escribir "Masaje deportivo"
⏱️ Esperar respuesta
💾 Verificar HumanHandoffRequest creado
💾 Verificar status=PENDING
💾 Verificar client_interests registrado
🔔 Verificar notificación a staff
```

## BOT-005: Handoff - Usuario Anónimo Sin Datos (Sad Path -> Recolección)
```
➡️ Usuario anónimo sin nombre/teléfono
📱 Escribir "Quiero hablar con alguien"
⏱️ Esperar respuesta
✅ Verificar bot solicita WhatsApp
📱 Escribir "+573001234567"
⏱️ Esperar respuesta
✅ Verificar bot confirma y crea handoff
💾 Verificar AnonymousUser.phone_number actualizado
💾 Verificar HumanHandoffRequest creado
```

## BOT-006: Detección de Toxicidad Nivel 1 (Happy Path)
```
➡️ Login como CLIENT
📱 Escribir mensaje con coqueteo leve
⏱️ Esperar respuesta
✅ Verificar bot reencausa a servicios del spa
💾 Verificar analysis.toxicity_level=1
💾 Verificar was_blocked=False
```

## BOT-007: Detección de Toxicidad Nivel 2 - Advertencia (Sad Path)
```
➡️ Login como CLIENT
📱 Escribir mensaje con insinuación sexual clara
⏱️ Esperar respuesta
✅ Verificar bot da advertencia profesional
💾 Verificar analysis.toxicity_level=2
💾 Verificar was_blocked=False
```

## BOT-008: Detección de Toxicidad Nivel 3 - Bloqueo (Sad Path)
```
➡️ Login como CLIENT
📱 Escribir mensaje con acoso explícito
⏱️ Esperar respuesta
✅ Verificar bot bloquea conversación
💾 Verificar analysis.toxicity_level=3
💾 Verificar was_blocked=True
💾 Verificar block_reason="acoso"
🔔 Verificar alerta a admin
```

## BOT-009: Pregunta Fuera de Scope (Happy Path)
```
➡️ Login como CLIENT
📱 Escribir "Cuál es la capital de Francia?"
⏱️ Esperar respuesta
✅ Verificar bot indica que no puede responder eso
✅ Verificar reencausa a servicios del spa
```

## BOT-010: Rate Limiting de Bot (Sad Path)
```
➡️ Login como CLIENT
📱 Enviar 6 mensajes en 1 minuto (límite=5/min)
✅ Verificar error 429 Too Many Requests
✅ Verificar mensaje "Has enviado demasiados mensajes"
```

## BOT-011: Respuesta a Notificación Previa (Happy Path)
```
➡️ Usuario recibe notificación de cita confirmada
➡️ Usuario responde por WhatsApp "A qué hora es?"
🔄 Webhook recibe mensaje
💾 Verificar extra_context con last_notification
⏱️ Esperar respuesta de bot
✅ Verificar bot tiene contexto de la cita
✅ Verificar respuesta incluye hora de cita
```

## BOT-012: Staff Responde a Handoff (Happy Path)
```
➡️ Login como STAFF
➡️ Navegar a /admin/handoffs
✅ Verificar lista de handoffs pendientes
➡️ Click en handoff específico
📱 Escribir respuesta "Hola, en qué puedo ayudarte?"
➡️ Click en "Enviar"
💾 Verificar HumanMessage creado
💾 Verificar HumanHandoffRequest.status=IN_PROGRESS
🔔 Verificar notificación al cliente
```

## BOT-013: Resolver Handoff (Happy Path)
```
➡️ Continuar conversación de handoff
➡️ Click en "Resolver"
💾 Verificar HumanHandoffRequest.status=RESOLVED
💾 Verificar resolved_at
✅ Verificar métricas de tiempo de resolución
```

---

# 🟢 MÓDULO: ANALYTICS Y REPORTES

## ANALYTICS-001: Dashboard de KPIs (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/analytics
📱 Seleccionar rango de fechas
➡️ Click en "Generar Reporte"
✅ Verificar conversion_rate mostrado
✅ Verificar no_show_rate mostrado
✅ Verificar reschedule_rate mostrado
✅ Verificar utilization_rate mostrado
✅ Verificar LTV por rol mostrado
✅ Verificar ingresos totales
```

## ANALYTICS-002: Filtrar por Staff (Happy Path)
```
➡️ En dashboard de analytics
📱 Seleccionar staff específico
➡️ Click en "Aplicar Filtro"
✅ Verificar KPIs filtrados por ese staff
✅ Verificar utilización solo de ese staff
```

## ANALYTICS-003: Filtrar por Categoría de Servicio (Happy Path)
```
➡️ En dashboard de analytics
📱 Seleccionar categoría "Masajes Relajantes"
➡️ Click en "Aplicar Filtro"
✅ Verificar KPIs filtrados por categoría
```

## ANALYTICS-004: Ver Detalle de Ventas (Happy Path)
```
➡️ En dashboard de analytics
➡️ Click en "Ver Detalle de Ventas"
✅ Verificar tabla con órdenes
✅ Verificar columnas: ID, Usuario, Estado, Total, Fecha
✅ Verificar paginación funcionando
```

## ANALYTICS-005: Ver Deuda y Recuperación (Happy Path)
```
➡️ En dashboard de analytics
➡️ Navegar a sección "Cartera"
✅ Verificar deuda total
✅ Verificar monto recuperado
✅ Verificar tasa de recuperación
✅ Verificar lista de pagos en mora
```

## ANALYTICS-006: Exportar Reporte (Happy Path)
```
➡️ En dashboard de analytics
📱 Seleccionar formato CSV/Excel
➡️ Click en "Exportar"
✅ Verificar descarga de archivo
✅ Verificar contenido correcto
💾 Verificar AuditLog de exportación
```

---

# 🟢 MÓDULO: ADMINISTRACIÓN

## ADMIN-001: Marcar Usuario como CNG (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/users/[phone]
➡️ Click en "Marcar como Persona Non Grata"
📱 Ingresar notas internas
📱 Subir foto (opcional)
➡️ Click en "Confirmar"
💾 Verificar user.is_persona_non_grata=True
💾 Verificar user.is_active=False
💾 Verificar BlockedPhoneNumber creado
💾 Verificar todas las sesiones revocadas
💾 Verificar citas futuras canceladas
💾 Verificar AuditLog FLAG_NON_GRATA
💾 Verificar AdminNotification creada
🔔 Verificar notificación al usuario
```

## ADMIN-002: Cancelar Cita como Admin (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/appointments/[id]
➡️ Click en "Cancelar Cita"
📱 Ingresar motivo
➡️ Click en "Confirmar"
💾 Verificar Appointment.status=CANCELLED
💾 Verificar Appointment.outcome=CANCELLED_BY_ADMIN
💾 Verificar AuditLog ADMIN_CANCEL_APPOINTMENT
🔔 Verificar notificación al cliente
🔄 Verificar oferta a waitlist
```

## ADMIN-003: Crear Ajuste Financiero - Crédito (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/users/[id]/adjustments
➡️ Click en "Nuevo Ajuste"
📱 Seleccionar tipo "CREDIT"
📱 Ingresar monto $50,000
📱 Ingresar razón "Compensación por inconveniente"
➡️ Click en "Crear"
💾 Verificar FinancialAdjustment creado
💾 Verificar ClientCredit creado
💾 Verificar AuditLog FINANCIAL_ADJUSTMENT_CREATED
🔔 Verificar notificación al usuario
```

## ADMIN-004: Ajuste Financiero - Excede Límite (Sad Path)
```
➡️ Login como ADMIN
➡️ Intentar crear ajuste por $6,000,000 (límite $5,000,000)
✅ Verificar error "El monto excede el límite permitido"
```

## ADMIN-005: Ver Logs de Auditoría (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/audit-logs
✅ Verificar lista de acciones auditadas
📱 Filtrar por acción "FLAG_NON_GRATA"
✅ Verificar resultados filtrados
📱 Filtrar por usuario objetivo
✅ Verificar resultados filtrados
```

## ADMIN-006: Gestionar GlobalSettings (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/settings
📱 Modificar advance_payment_percentage a 30
📱 Modificar appointment_buffer_time a 15
➡️ Click en "Guardar"
✅ Verificar cambios aplicados
💾 Verificar cache invalidado
✅ Verificar log de cambios importantes
```

## ADMIN-007: GlobalSettings - Validación de Comisión (Sad Path)
```
➡️ Login como ADMIN
➡️ Intentar reducir developer_commission_percentage
✅ Verificar error "No se permite disminuir la comisión del desarrollador"
```

## ADMIN-008: Ver Notificaciones Administrativas (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/notifications
✅ Verificar lista de AdminNotification
✅ Verificar filtro por tipo (PAGOS, SUSCRIPCIONES, USUARIOS)
➡️ Click en notificación
✅ Verificar marcada como leída
```

## ADMIN-009: Gestionar Templates de Notificación (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/notification-templates
➡️ Click en template existente
📱 Modificar body_template
➡️ Click en "Guardar"
💾 Verificar versión histórica creada
✅ Verificar preview de template
```

## ADMIN-010: Gestionar Consentimientos (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/consent-templates
➡️ Click en "Nueva Versión"
📱 Ingresar título
📱 Ingresar cuerpo legal
📱 Marcar como activo
➡️ Click en "Publicar"
💾 Verificar ConsentTemplate creado
💾 Verificar version incrementado
✅ Verificar template anterior desactivado
```

## ADMIN-011: Anonimizar Perfil GDPR (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/users/[phone]/profile
➡️ Click en "Anonimizar Perfil (GDPR)"
✅ Verificar advertencia de acción irreversible
📱 Confirmar escribiendo "ANONIMIZAR"
➡️ Click en "Confirmar"
💾 Verificar user.first_name="ANONIMIZADO"
💾 Verificar profile.medical_conditions=""
💾 Verificar historial eliminado
💾 Verificar AuditLog CLINICAL_PROFILE_ANONYMIZED
```

## ADMIN-012: Ver Dashboard de Comisiones (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/finances/commissions
✅ Verificar deuda total al desarrollador
✅ Verificar lista de CommissionLedger
✅ Verificar estado de mora
✅ Verificar última dispersión
```

## ADMIN-013: Bloquear IP Manualmente (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/security/blocked-ips
➡️ Click en "Bloquear IP"
📱 Ingresar IP
📱 Seleccionar duración (1 hora)
➡️ Click en "Bloquear"
💾 Verificar cache key blocked_ip:X.X.X.X
✅ Verificar IP en lista de bloqueados
```

## ADMIN-014: Exportar Usuarios (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/users
➡️ Click en "Exportar CSV"
✅ Verificar descarga de archivo
✅ Verificar columnas: ID, Phone, Email, Role, Status, Created
💾 Verificar AuditLog de exportación
```

## ADMIN-015: Ver Actividad Sospechosa (Happy Path)
```
➡️ Login como ADMIN
➡️ Navegar a /admin/security/suspicious
✅ Verificar lista de SuspiciousActivity
✅ Verificar IPs con múltiples intentos fallidos
✅ Verificar patrones de abuso detectados
➡️ Click en IP específica
✅ Verificar historial de esa IP
➡️ Click en "Bloquear"
💾 Verificar IPBlocklist creado
```

---

# 🟢 MÓDULO: FINANZAS Y PAGOS

## FIN-001: Webhook Wompi - Pago Aprobado (Happy Path)
```
🔄 Wompi envía webhook transaction.updated APPROVED
✅ Verificar firma validada correctamente
💾 Verificar Payment.status=APPROVED
💾 Verificar lógica de negocio ejecutada (confirmar cita, etc.)
💾 Verificar WebhookEvent.status=PROCESSED
💾 Verificar CommissionLedger creado
```

## FIN-002: Webhook Wompi - Firma Inválida (Sad Path)
```
🔄 Webhook con firma manipulada
✅ Verificar error 400 "Firma del webhook inválida"
💾 Verificar WebhookEvent.status=FAILED
💾 Verificar log de seguridad
```

## FIN-003: Webhook Wompi - Monto No Coincide (Sad Path)
```
🔄 Webhook con amount_in_cents diferente al esperado
💾 Verificar Payment.status=ERROR
💾 Verificar WebhookEvent.status=FAILED
🔔 Verificar alerta de fraude
```

## FIN-004: Dispersión Automática al Desarrollador (Happy Path)
```
💾 CommissionLedger acumulado > threshold
🔄 Task evaluate_payout ejecutada
💾 Verificar balance consultado en Wompi
💾 Verificar payout creado
💾 Verificar CommissionLedger.status=PAID
💾 Verificar wompi_transfer_id guardado
💾 Verificar developer_in_default=False
```

## FIN-005: Dispersión - Fondos Insuficientes (Sad Path)
```
💾 Deuda > balance disponible
🔄 Task evaluate_payout ejecutada
💾 Verificar payout parcial (si posible) o fallo
💾 Verificar developer_in_default=True
💾 Verificar CommissionLedger.status=FAILED_NSF
🔔 Verificar alerta de mora
```

## FIN-006: Crédito Expirado (Sad Path)
```
💾 ClientCredit con expires_at = ayer
➡️ Intentar usar crédito
✅ Verificar crédito no aplicado
💾 Verificar ClientCredit.status=EXPIRED
```

---

# 🟢 PRUEBAS DE SEGURIDAD

## SEC-001: SQL Injection en Búsqueda
```
➡️ Navegar a /shop?search=' OR '1'='1
✅ Verificar error 400 o resultados vacíos
✅ Verificar NO se expone error de BD
```

## SEC-002: XSS en Campos de Texto
```
📱 Ingresar <script>alert('XSS')</script> en notas
➡️ Guardar y ver
✅ Verificar script escapado/no ejecutado
```

## SEC-003: CSRF Token Requerido
```
➡️ Hacer POST sin CSRF token
✅ Verificar error 403 Forbidden
```

## SEC-004: JWT Expirado
```
⏱️ Esperar expiración de access_token
➡️ Hacer request con token expirado
✅ Verificar error 401 Unauthorized
```

## SEC-005: Acceso a Recurso de Otro Usuario
```
➡️ Login como USER-A
➡️ Intentar ver cita de USER-B
✅ Verificar error 403 o 404
```

## SEC-006: Escalación de Privilegios
```
➡️ Login como CLIENT
➡️ Intentar acceder a /admin/users
✅ Verificar error 403 Forbidden
```

## SEC-007: Rate Limiting Global
```
➡️ Enviar 101 requests en 1 minuto (límite=100)
✅ Verificar error 429 Too Many Requests
✅ Verificar header Retry-After
```

## SEC-008: Fuerza Bruta en Login
```
➡️ Intentar 10 logins fallidos seguidos
✅ Verificar cuenta bloqueada temporalmente
✅ Verificar reCAPTCHA requerido
```

---

# 🟢 PRUEBAS DE RENDIMIENTO

## PERF-001: Tiempo de Respuesta de Catálogo
```
➡️ GET /api/v1/services con 100 servicios
✅ Verificar respuesta < 500ms
✅ Verificar paginación funcional
```

## PERF-002: Creación de Cita Concurrente
```
➡️ 10 usuarios intentan reservar mismo slot simultáneamente
✅ Verificar solo 1 éxito
✅ Verificar 9 errores de conflicto
✅ Verificar NO race conditions
```

## PERF-003: Webhook bajo Carga
```
➡️ Enviar 100 webhooks en 10 segundos
✅ Verificar todos procesados correctamente
✅ Verificar idempotencia respetada
```

## PERF-004: Dashboard de Analytics
```
➡️ Generar reporte de 1 año de datos
✅ Verificar respuesta < 5 segundos
✅ Verificar cache utilizado en requests subsecuentes
```

---

*Total de Pruebas E2E Diseñadas: 180+*
*Cobertura Estimada: 95% de flujos críticos*
