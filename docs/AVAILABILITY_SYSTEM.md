# Sistema de Disponibilidad de Horarios - Studio Zens

## 📋 Resumen

Este documento describe el sistema de disponibilidad de horarios para citas, incluyendo las responsabilidades del backend y frontend, y cómo integrarlos.

---

## 🔧 Configuración del Sistema

### Parámetros Clave

| Parámetro | Valor | Configurable en |
|-----------|-------|-----------------|
| **Buffer entre citas** | 15 minutos | `GlobalSettings.appointment_buffer_time` |
| **Anticipación mínima** | 30 minutos | Hardcoded en `AvailabilityService` |
| **Intervalo de slots** | 15 minutos | `AvailabilityService.SLOT_INTERVAL_MINUTES` |

### Reglas de Negocio

1. ✅ **Se puede agendar el mismo día** si:
   - El horario de inicio es al menos **30 minutos** en el futuro

2. ✅ **Los slots solo aparecen si**:
   - `start_time >= now() + 30 minutos`
   - `duración_servicio + 15 min buffer` cabe en el hueco disponible
   - El staff tiene disponibilidad configurada para ese día/hora
   - No hay citas confirmadas que se solapen (incluyendo buffer)

3. ✅ **Anonimización de staff**:
   - El backend NO expone nombres reales del personal
   - Retorna etiquetas genéricas: `"Terapeuta 1"`, `"Terapeuta 2"`, etc.

---

## 🎯 Responsabilidades

### Backend

El backend calcula y valida **TODO** lo relacionado con disponibilidad:

- ✅ Calcular slots disponibles por staff
- ✅ Aplicar buffer de 15 min antes/después de cada cita
- ✅ Filtrar slots que ya pasaron o están a menos de 30 min
- ✅ Validar que la duración + buffer quepa en el bloque disponible
- ✅ Anonimizar identificación del staff (`staff_label` en lugar de nombres)
- ✅ Validar al crear la cita que el slot siga disponible
- ✅ Prevenir doble booking con locks de base de datos

### Frontend

El frontend solo **presenta** y **envía selecciones**:

- Consultar slots disponibles por fecha y servicios
- Agrupar slots por `staff_id` (usando `staff_label` para mostrar)
- Mostrar horarios en columnas sin exponer nombres del staff
- Permitir al usuario seleccionar un horario
- Enviar la solicitud de creación de cita al backend

---

## 📡 Integración Frontend ↔ Backend

### 1️⃣ Consultar Disponibilidad

**Endpoint:** `GET /api/v1/appointments/availability/`

**Query Parameters:**
```
service_ids: uuid1,uuid2  (obligatorio, puede ser uno o varios)
date: YYYY-MM-DD          (obligatorio)
staff_member_id: uuid     (opcional, para filtrar por staff específico)
```

**Ejemplo Request:**
```http
GET /api/v1/appointments/availability/?service_ids=9ca27ec0-98ab-4f70-bf69-90f043330803&date=2025-12-15
Authorization: Bearer <token>
```

**Ejemplo Response:**
```json
[
  {
    "start_time": "2025-12-15T08:00:00-05:00",
    "staff_id": "4a13c1a0-8b07-4555-8fc7-5387ccd22c1e",
    "staff_label": "Terapeuta 1"
  },
  {
    "start_time": "2025-12-15T08:00:00-05:00",
    "staff_id": "bad35106-3c2f-4a8d-9f1e-8a7b6c5d4e3f",
    "staff_label": "Terapeuta 2"
  },
  {
    "start_time": "2025-12-15T08:15:00-05:00",
    "staff_id": "4a13c1a0-8b07-4555-8fc7-5387ccd22c1e",
    "staff_label": "Terapeuta 1"
  }
]
```

**Estructura de cada slot:**
- `start_time` (string ISO 8601): Hora de inicio del slot
- `staff_id` (UUID): ID interno del staff (necesario para crear la cita)
- `staff_label` (string): Etiqueta anónima del terapeuta ("Terapeuta 1", "Terapeuta 2", etc.)

---

### 2️⃣ Agrupar Slots en el Frontend

El frontend debe agrupar los slots por `staff_id` para mostrarlos en columnas:

**Ejemplo en JavaScript:**
```javascript
const response = await fetch('/api/v1/appointments/availability/?service_ids=uuid&date=2025-12-15');
const slots = await response.json();

// Agrupar por staff_id
const groupedByStaff = slots.reduce((acc, slot) => {
  const staffId = slot.staff_id;

  if (!acc[staffId]) {
    acc[staffId] = {
      label: slot.staff_label,  // "Terapeuta 1"
      times: []
    };
  }

  acc[staffId].times.push({
    startTime: slot.start_time,
    staffId: slot.staff_id  // Guardar para enviar al backend
  });

  return acc;
}, {});

// Renderizar columnas
Object.values(groupedByStaff).forEach(staff => {
  console.log(`${staff.label}:`);
  staff.times.forEach(slot => {
    console.log(`  ${new Date(slot.startTime).toLocaleTimeString()}`);
  });
});
```

**Salida esperada:**
```
Terapeuta 1:
  08:00
  08:15
  08:30
  ...

Terapeuta 2:
  08:00
  08:15
  09:00
  ...
```

---

### 3️⃣ Crear Cita

Cuando el usuario selecciona un horario:

**Endpoint:** `POST /api/v1/appointments/`

**Request Body:**
```json
{
  "service_ids": ["9ca27ec0-98ab-4f70-bf69-90f043330803"],
  "start_time": "2025-12-15T08:00:00-05:00",
  "staff_member": "4a13c1a0-8b07-4555-8fc7-5387ccd22c1e"
}
```

**Campos:**
- `service_ids` (array de UUIDs): IDs de los servicios seleccionados
- `start_time` (string ISO 8601): Hora de inicio seleccionada
- `staff_member` (UUID): El `staff_id` del slot seleccionado

**Response Exitosa (201 Created):**
```json
{
  "id": "cita-uuid",
  "user": {...},
  "services": [...],
  "staff_member": {...},
  "start_time": "2025-12-15T08:00:00-05:00",
  "end_time": "2025-12-15T08:45:00-05:00",
  "status": "PENDING_PAYMENT",
  "price_at_purchase": "120000.00"
}
```

**Errores Comunes:**

```json
// 409 Conflict - El horario ya no está disponible
{
  "detail": "Horario no disponible por solapamiento.",
  "internal_code": "APP-001"
}

// 422 Unprocessable Entity - Usuario bloqueado
{
  "detail": "Usuario bloqueado por deuda pendiente.",
  "internal_code": "APP-004"
}

// 400 Bad Request - Validación
{
  "start_time": ["El horario seleccionado ya no está disponible."]
}
```

---

## 🧪 Ejemplos de Uso

### Ejemplo 1: Consultar disponibilidad para un servicio

```javascript
// 1. Usuario selecciona "Cráneo Facial Ensueño" y fecha "2025-12-15"
const serviceId = "9ca27ec0-98ab-4f70-bf69-90f043330803";
const date = "2025-12-15";

// 2. Consultar disponibilidad
const response = await fetch(
  `/api/v1/appointments/availability/?service_ids=${serviceId}&date=${date}`,
  {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }
);

const slots = await response.json();

// 3. Agrupar por staff
const byStaff = slots.reduce((acc, slot) => {
  if (!acc[slot.staff_id]) {
    acc[slot.staff_id] = {
      label: slot.staff_label,
      slots: []
    };
  }
  acc[slot.staff_id].slots.push(slot);
  return acc;
}, {});

// 4. Renderizar UI
// Terapeuta 1: [08:00, 08:15, 08:30, ...]
// Terapeuta 2: [08:00, 09:00, 10:00, ...]
```

### Ejemplo 2: Crear cita con slot seleccionado

```javascript
// Usuario hace clic en "08:00" de "Terapeuta 1"
const selectedSlot = {
  start_time: "2025-12-15T08:00:00-05:00",
  staff_id: "4a13c1a0-8b07-4555-8fc7-5387ccd22c1e"
};

// Crear cita
const createResponse = await fetch('/api/v1/appointments/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    service_ids: ["9ca27ec0-98ab-4f70-bf69-90f043330803"],
    start_time: selectedSlot.start_time,
    staff_member: selectedSlot.staff_id
  })
});

if (createResponse.ok) {
  const appointment = await createResponse.json();
  console.log('Cita creada:', appointment.id);
  // Redirigir a pago...
} else {
  const error = await createResponse.json();
  console.error('Error:', error.detail);
  // Mostrar mensaje al usuario
}
```

---

## ⚠️ Validaciones Importantes

### En el Backend (Ya implementadas)

1. ✅ **Anticipación mínima de 30 min**: No se retornan slots que empiecen en menos de 30 minutos
2. ✅ **Buffer de 15 min**: Se aplica antes y después de cada cita para evitar solapamientos
3. ✅ **Validación de disponibilidad en tiempo real**: Al crear la cita se vuelve a validar que el slot esté disponible
4. ✅ **Prevención de doble booking**: Usa `SELECT FOR UPDATE` para evitar condiciones de carrera

### En el Frontend (Recomendadas)

1. ⚠️ **Refrescar disponibilidad**: Si el usuario tarda mucho, refrescar los slots antes de crear la cita
2. ⚠️ **Manejo de errores**: Mostrar mensajes claros cuando un slot ya no está disponible
3. ⚠️ **Validación de fecha**: No permitir seleccionar fechas en el pasado

---

## 🔍 Troubleshooting

### No aparecen slots para hoy

**Causa**: Es normal si:
- La hora actual + 30 min supera los horarios de trabajo del staff
- Todos los horarios ya están ocupados

**Solución**: Verificar que existan horarios configurados en `StaffAvailability` para el día de la semana.

### Aparecen slots pero falla al crear la cita

**Causa**: Otro usuario tomó el slot entre la consulta y la creación.

**Solución**: El backend retorna error 409 con código `APP-001`. Mostrar mensaje al usuario y refrescar disponibilidad.

### No se agrupan correctamente por terapeuta

**Causa**: El frontend no está usando `staff_id` como clave de agrupación.

**Solución**: Agrupar por `slot.staff_id`, no por `slot.staff_label` (porque las etiquetas se regeneran en cada request y podrían cambiar el orden).

---

## 📝 Notas Técnicas

### ¿Por qué anonimizar el staff?

- **Privacidad**: Los clientes no necesitan conocer los nombres del personal
- **Flexibilidad**: Permite rotar staff sin afectar la UX
- **Simplicidad**: Evita que los clientes tengan preferencias que compliquen la asignación

### ¿Por qué enviar staff_id si está anonimizado?

- El `staff_id` es necesario para que el backend asigne correctamente la cita
- Las etiquetas (`Terapeuta 1`, etc.) son solo para presentación
- El frontend nunca debe mostrar el `staff_id` crudo al usuario

### ¿Cómo se asignan las etiquetas?

Las etiquetas se asignan secuencialmente en el orden en que aparecen los slots:
- Primer staff que tenga slots → `Terapeuta 1`
- Segundo staff → `Terapeuta 2`
- etc.

**Importante**: Las etiquetas pueden cambiar entre requests (si cambia el orden de los staff). Por eso el frontend debe agrupar por `staff_id`, no por `staff_label`.

---

## ✅ Checklist de Implementación Frontend

- [ ] Implementar llamada a `/api/v1/appointments/availability/`
- [ ] Agrupar slots por `staff_id`
- [ ] Mostrar columnas con `staff_label` sin exponer nombres reales
- [ ] Guardar `staff_id` del slot seleccionado
- [ ] Enviar `service_ids`, `start_time` y `staff_member` al crear cita
- [ ] Manejar error 409 (slot ya no disponible)
- [ ] Manejar error 422 (usuario bloqueado por deuda)
- [ ] Refrescar disponibilidad si el usuario tarda en decidir

---

## 📚 Referencias

- Servicio: [spa/services/appointments.py:41-215](../spa/services/appointments.py)
- Serializer: [spa/serializers/appointment.py:208-248](../spa/serializers/appointment.py)
- Vista: [spa/views/appointments/availability.py:13-26](../spa/views/appointments/availability.py)
- Tests: [spa/tests/test_services_appointments.py](../spa/tests/test_services_appointments.py)
