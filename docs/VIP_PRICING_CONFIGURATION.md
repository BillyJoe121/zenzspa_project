# Configuración de Precios VIP - StudioZens

## 💰 Configuración Actual

### Precio de Membresía
- **Precio mensual VIP**: $39,900 COP
- **Descuento en servicios**: 15% sobre precio regular
- **Descuento en productos**: 15% sobre precio regular (cuando se implemente marketplace)

---

## 📊 Análisis de Precios por Servicio

| Servicio | Precio Regular | Precio VIP | Ahorro |
|----------|----------------|------------|--------|
| Cráneo Facial Ensueño | $120,000 | $102,000 | $18,000 |
| Cráneo Facial Ocaso | $130,000 | $110,500 | $19,500 |
| Cráneo Facial Renacer | $145,000 | $123,250 | $21,750 |
| Drenaje Linfático | $140,000 | $119,000 | $21,000 |
| Experiencia Zen | $135,000 | $114,750 | $20,250 |
| Herbal Essence | $145,000 | $123,250 | $21,750 |
| Hidra Facial | $180,000 | $153,000 | $27,000 |
| Limpieza Facial Sencilla | $110,000 | $93,500 | $16,500 |
| Pediluvio | $80,000 | $68,000 | $12,000 |
| Terapia de Equilibrio | $155,000 | $131,750 | $23,250 |
| Terapéutico Completo | $150,000 | $127,500 | $22,500 |
| Terapéutico Focalizado | $130,000 | $110,500 | $19,500 |
| Terapéutico Mixto | $145,000 | $123,250 | $21,750 |
| Toque de Seda | $145,000 | $123,250 | $21,750 |
| Udvartana | $170,000 | $144,500 | $25,500 |
| Zen Extendido | $165,000 | $140,250 | $24,750 |

---

## 📈 Punto de Equilibrio

### Análisis Financiero

- **Ahorro promedio por servicio**: $21,047 COP
- **Servicios necesarios para recuperar inversión**: ~2 servicios/mes
- **Valor anual de la membresía**: $478,800 COP

### Escenarios de ROI para el Cliente

#### Cliente Frecuente (2 servicios/mes)
```
Ahorro mensual estimado: $42,094
Costo membresía: $39,900
Ganancia neta: $2,194/mes
ROI anual: $26,328
```

#### Cliente Regular (3 servicios/mes)
```
Ahorro mensual estimado: $63,141
Costo membresía: $39,900
Ganancia neta: $23,241/mes
ROI anual: $278,892
```

#### Cliente Premium (4+ servicios/mes)
```
Ahorro mensual estimado: $84,188+
Costo membresía: $39,900
Ganancia neta: $44,288+/mes
ROI anual: $531,456+
```

---

## 🎯 Estrategia de Precio

### Por qué $39,900/mes?

1. **Precio psicológico**: Justo debajo de $40,000 (precio de referencia)
2. **Competitivo**: Similar a membresías de gimnasios premium en Colombia
3. **Punto de equilibrio bajo**: Solo 2 servicios/mes para recuperar inversión
4. **Valor percibido alto**: 15% de descuento constante + beneficios adicionales

### Beneficios Adicionales VIP

Además del 15% de descuento, los miembros VIP reciben:

1. **Recompensa de Lealtad**:
   - Servicio gratuito cada 3 meses de membresía continua
   - Configurable en: `loyalty_months_required`
   - Servicio de recompensa: Configurable en admin

2. **Prioridad en Reservas**:
   - Acceso preferencial a horarios
   - Notificaciones anticipadas de nuevos servicios

3. **Status Premium**:
   - Badge VIP en la aplicación
   - Reconocimiento especial

---

## 🔧 Configuración Técnica

### Variables de Sistema

```python
# GlobalSettings
vip_monthly_price = Decimal('39900.00')  # COP
loyalty_months_required = 3              # meses
credit_expiration_days = 365             # días
```

### Cálculo de Precio VIP

```python
# Fórmula aplicada a cada servicio
vip_price = regular_price * (1 - 0.15)
vip_price = regular_price * 0.85
```

### Servicios Actualizados

Total de servicios con precio VIP: **16 servicios activos**

---

## 📱 Cómo se Aplica en el Frontend

### 1. Visualización de Precios

```tsx
{user.is_vip ? (
  <>
    <span className="original-price">${service.price}</span>
    <span className="vip-price">${service.vip_price}</span>
    <span className="savings">Ahorras ${service.price - service.vip_price}</span>
  </>
) : (
  <>
    <span className="price">${service.price}</span>
    {service.vip_price && (
      <div className="vip-promotion">
        <p>Precio VIP: ${service.vip_price}</p>
        <a href="/vip">Hazte VIP y ahorra 15%</a>
      </div>
    )}
  </>
)}
```

### 2. Endpoint para Obtener Precio VIP

```typescript
// GET /api/v1/settings/
{
  "vip_monthly_price": "39900.00",
  "loyalty_months_required": 3,
  // ...
}
```

---

## 🔄 Actualización de Precios

### Script de Configuración

Para volver a ejecutar el script de configuración:

```bash
python scripts/configure_vip_pricing.py
```

Este script:
1. ✅ Establece el precio mensual VIP en $39,900
2. ✅ Calcula y aplica 15% de descuento a todos los servicios activos
3. ✅ Muestra resumen con punto de equilibrio
4. ✅ Es idempotente (se puede ejecutar múltiples veces sin problema)

### Actualización Manual desde Admin

1. Ve a: `http://localhost:8000/admin/core/globalsettings/`
2. Modifica `vip_monthly_price`
3. Guarda cambios

Para actualizar precios VIP de servicios individuales:

1. Ve a: `http://localhost:8000/admin/spa/service/`
2. Edita el campo `vip_price` de cada servicio
3. Guarda cambios

---

## 📊 Métricas Clave para Monitorear

### KPIs Recomendados

1. **Tasa de Conversión VIP**
   - Clientes regulares que se convierten en VIP
   - Meta sugerida: 15-20%

2. **Tasa de Retención VIP**
   - VIPs que renuevan mensualmente
   - Meta sugerida: 80%+

3. **Frecuencia de Uso**
   - Servicios promedio por VIP/mes
   - Meta sugerida: 2.5-3 servicios

4. **Lifetime Value (LTV) VIP**
   - Valor total generado por cliente VIP
   - Calcular: (Avg servicios/mes × Precio promedio × Meses activo)

5. **Churn Rate**
   - VIPs que cancelan auto-renovación
   - Meta sugerida: <20%/mes

---

## 💡 Recomendaciones de Marketing

### Mensajes Clave

**Para Clientes Nuevos:**
- "Con solo 2 servicios al mes, recuperas tu inversión"
- "15% de descuento en TODO + servicio gratis cada 3 meses"
- "Menos de $40,000/mes para disfrutar tratamientos premium"

**Para Clientes Existentes:**
- "¿Visitas StudioZens 2 veces al mes? Hazte VIP y ahorra"
- "Calcula tu ahorro: [Servicios mensuales] × $21,000 = Ahorro VIP"
- "Membresía VIP = Acceso ilimitado a precios especiales"

### Páginas de Conversión

1. **/vip** - Landing con calculadora de ahorro
2. **/vip/calculator** - Herramienta para calcular ROI personalizado
3. **/services** - Mostrar prominentemente precio VIP en cada servicio

---

## 🎁 Bonificaciones Sugeridas (Opcional)

Para incrementar conversiones, considera:

1. **Primer mes gratis** para clientes con historial de 3+ citas
2. **Descuento anual**: 12 meses por el precio de 10 ($399,000/año)
3. **Referidos VIP**: 1 mes gratis por cada amigo que se haga VIP
4. **Cumpleaños VIP**: Servicio adicional gratis en tu mes de cumpleaños

---

## 📅 Revisión de Precios

Se recomienda revisar la estructura de precios VIP:

- **Trimestral**: Analizar métricas de conversión y retención
- **Semestral**: Evaluar competencia y ajustar si es necesario
- **Anual**: Revisión completa de la estrategia VIP

---

**Última actualización**: 13 de Diciembre, 2024
**Configurado por**: Sistema automatizado
**Estado**: ✅ Activo y funcionando
