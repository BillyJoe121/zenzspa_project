# 🧪 Pruebas E2E - Rendimiento

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

## PERF-001: Tiempo de Respuesta de Catálogo (Happy Path)
```
➡️ GET /api/v1/services con 100 servicios
✅ Verificar respuesta < 500ms
✅ Verificar paginación funcional
```

## PERF-002: Creación de Cita Concurrente (Happy Path)
```
➡️ 10 usuarios intentan reservar mismo slot simultáneamente
✅ Verificar solo 1 éxito
✅ Verificar 9 errores de conflicto
✅ Verificar NO race conditions
```

## PERF-003: Webhook bajo Carga (Happy Path)
```
➡️ Enviar 100 webhooks en 10 segundos
✅ Verificar todos procesados correctamente
✅ Verificar idempotencia respetada
```

## PERF-004: Dashboard de Analytics (Happy Path)
```
➡️ Generar reporte de 1 año de datos
✅ Verificar respuesta < 5 segundos
✅ Verificar cache utilizado en requests subsecuentes
```
