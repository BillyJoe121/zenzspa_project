# 🧪 Pruebas E2E - Analytics y Reportes

## 📋 Convenciones

- ✅ = Verificación/Assertion
- ➡️ = Navegación/Acción
- 📱 = Input del usuario
- 🔔 = Notificación esperada
- ⏱️ = Espera/Delay
- 🔄 = Refresh/Polling
- 💾 = Persistencia verificada en BD

---

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
