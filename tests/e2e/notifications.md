# 🧪 Pruebas E2E - Notificaciones

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
