# 🧪 Pruebas E2E - Perfil Clínico

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
