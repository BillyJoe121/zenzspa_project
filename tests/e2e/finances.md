# 🧪 Pruebas E2E - Finanzas y Pagos

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
