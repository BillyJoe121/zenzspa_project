# 🧪 Pruebas E2E - Suscripción VIP

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
