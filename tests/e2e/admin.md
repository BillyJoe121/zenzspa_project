# 🧪 Pruebas E2E - Administración

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
