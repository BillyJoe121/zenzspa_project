# 🧪 Pruebas E2E - Bot Conversacional

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
📱 Escribir "+573157589548"
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
