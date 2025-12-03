# 🧪 Pruebas E2E - Paquetes y Vouchers

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
