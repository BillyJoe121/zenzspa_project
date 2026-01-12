# 🧪 Pruebas E2E - Servicios y Citas

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
