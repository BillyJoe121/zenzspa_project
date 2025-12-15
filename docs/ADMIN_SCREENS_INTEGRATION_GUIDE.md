# Guía de Integración: Pantallas de Administración

Esta guía detalla cómo conectar las pantallas de administración del frontend con los endpoints del backend.

---

## 🎯 Pantallas Prioritarias

### 1. Dashboard Staff/Admin (SCREEN-042)
### 2. Calendario de Citas (SCREEN-043)
### 3. Lista de Citas (SCREEN-044 y SCREEN-045)

---

## 📋 Tabla de Contenidos

1. [Autenticación y Permisos](#autenticación-y-permisos)
2. [Dashboard Staff/Admin](#1-dashboard-staffadmin-screen-042)
3. [Calendario de Citas](#2-calendario-de-citas-screen-043)
4. [Lista de Citas](#3-lista-de-citas-screen-044-y-screen-045)
5. [Tipos TypeScript](#tipos-typescript)
6. [Hooks Reutilizables](#hooks-reutilizables)

---

## 🔐 Autenticación y Permisos

### Verificación de Rol

Todas las pantallas de admin requieren que el usuario tenga rol `STAFF` o `ADMIN`.

```typescript
// hooks/useAuth.ts
export const useAuth = () => {
  const user = useSelector((state: RootState) => state.auth.user);
  
  const isStaff = user?.role === 'STAFF' || user?.role === 'ADMIN';
  const isAdmin = user?.role === 'ADMIN';
  
  return { user, isStaff, isAdmin };
};
```

### Protección de Rutas

```typescript
// components/ProtectedRoute.tsx
import { useAuth } from '@/hooks/useAuth';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export const StaffRoute = ({ children }: { children: React.ReactNode }) => {
  const { isStaff } = useAuth();
  const router = useRouter();
  
  useEffect(() => {
    if (!isStaff) {
      router.push('/login');
    }
  }, [isStaff, router]);
  
  if (!isStaff) return null;
  
  return <>{children}</>;
};
```

---

## 1. Dashboard Staff/Admin (SCREEN-042)

### Descripción
Pantalla de aterrizaje que muestra un resumen ejecutivo de la operación diaria.

### Endpoints Disponibles

#### 1.1 KPIs del Día
```typescript
GET /api/v1/analytics/kpis/
```

**Query Parameters:**
- `start_date`: YYYY-MM-DD (default: hoy - 6 días)
- `end_date`: YYYY-MM-DD (default: hoy)
- `staff_id`: UUID (opcional, filtrar por terapeuta)
- `force_refresh`: boolean (opcional, invalidar caché)

**Response:**
```json
{
  "total_revenue": 1250000,
  "total_appointments": 15,
  "avg_ticket": 83333,
  "completion_rate": 0.93,
  "cancellation_rate": 0.07,
  "no_show_rate": 0.00,
  "new_clients": 3,
  "returning_clients": 12,
  "vip_clients": 5,
  "debt_recovery": {
    "total_pending": 450000,
    "recovered_this_period": 200000
  },
  "growth": {
    "revenue_growth": 0.15,
    "appointments_growth": 0.10
  },
  "start_date": "2025-12-08",
  "end_date": "2025-12-14",
  "_cached_at": "2025-12-14T08:30:00Z"
}
```

#### 1.2 Agenda del Día
```typescript
GET /api/v1/analytics/dashboard/agenda-today/
```

**Response:**
```json
{
  "count": 15,
  "next": null,
  "previous": null,
  "results": [
    {
      "appointment_id": "uuid",
      "start_time": "2025-12-14T09:00:00-05:00",
      "status": "CONFIRMED",
      "client": {
        "id": "uuid",
        "name": "María García",
        "phone": "+573101234567",
        "email": "maria@example.com"
      },
      "staff": {
        "id": "uuid",
        "name": "Andrea Calma",
        "phone": "+573102000001",
        "email": "andrea@studiozens.com"
      },
      "has_debt": false
    }
  ]
}
```

#### 1.3 Pagos Pendientes
```typescript
GET /api/v1/analytics/dashboard/pending-payments/
```

**Response:**
```json
{
  "results": [
    {
      "type": "payment",
      "payment_id": "uuid",
      "amount": 50000,
      "user": {
        "id": "uuid",
        "name": "Carlos López",
        "phone": "+573109876543",
        "email": "carlos@example.com"
      },
      "created_at": "2025-12-14T10:00:00Z"
    },
    {
      "type": "appointment",
      "appointment_id": "uuid",
      "user": {
        "id": "uuid",
        "name": "Ana Martínez",
        "phone": "+573108765432",
        "email": "ana@example.com"
      },
      "start_time": "2025-12-14T14:00:00-05:00",
      "amount_due": 75000
    }
  ]
}
```

#### 1.4 Créditos por Vencer
```typescript
GET /api/v1/analytics/dashboard/expiring-credits/
```

**Response:**
```json
{
  "results": [
    {
      "credit_id": "uuid",
      "user": {
        "id": "uuid",
        "name": "Laura Pérez",
        "phone": "+573107654321",
        "email": "laura@example.com"
      },
      "remaining_amount": 120000,
      "expires_at": "2025-12-20"
    }
  ]
}
```

### Implementación Frontend

```typescript
// app/admin/dashboard/page.tsx
'use client';

import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { StaffRoute } from '@/components/ProtectedRoute';

interface DashboardKPIs {
  total_revenue: number;
  total_appointments: number;
  avg_ticket: number;
  completion_rate: number;
  new_clients: number;
  growth: {
    revenue_growth: number;
    appointments_growth: number;
  };
}

interface AgendaItem {
  appointment_id: string;
  start_time: string;
  status: string;
  client: {
    name: string;
    phone: string;
  };
  staff: {
    name: string;
  };
  has_debt: boolean;
}

export default function AdminDashboard() {
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        // Fetch en paralelo
        const [kpisRes, agendaRes] = await Promise.all([
          api.get('/analytics/kpis/', {
            params: {
              start_date: new Date().toISOString().split('T')[0],
              end_date: new Date().toISOString().split('T')[0],
            },
          }),
          api.get('/analytics/dashboard/agenda-today/'),
        ]);

        setKpis(kpisRes.data);
        setAgenda(agendaRes.data.results);
      } catch (error) {
        console.error('Error fetching dashboard:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (loading) return <div>Cargando...</div>;

  return (
    <StaffRoute>
      <div className="p-6">
        <h1 className="text-3xl font-bold mb-6">Dashboard</h1>

        {/* KPIs Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <KPICard
            title="Ingresos Hoy"
            value={`$${kpis?.total_revenue.toLocaleString('es-CO')}`}
            growth={kpis?.growth.revenue_growth}
          />
          <KPICard
            title="Citas Hoy"
            value={kpis?.total_appointments}
            growth={kpis?.growth.appointments_growth}
          />
          <KPICard
            title="Ticket Promedio"
            value={`$${kpis?.avg_ticket.toLocaleString('es-CO')}`}
          />
          <KPICard
            title="Clientes Nuevos"
            value={kpis?.new_clients}
          />
        </div>

        {/* Agenda del Día */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Agenda de Hoy</h2>
          <div className="space-y-2">
            {agenda.map((item) => (
              <div
                key={item.appointment_id}
                className="flex items-center justify-between p-4 border rounded hover:bg-gray-50"
              >
                <div>
                  <p className="font-medium">{item.client.name}</p>
                  <p className="text-sm text-gray-600">
                    {new Date(item.start_time).toLocaleTimeString('es-CO', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600">{item.staff.name}</p>
                  <StatusBadge status={item.status} />
                  {item.has_debt && (
                    <span className="text-xs text-red-600">⚠️ Deuda</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </StaffRoute>
  );
}

// Componente auxiliar
const KPICard = ({ title, value, growth }: any) => (
  <div className="bg-white rounded-lg shadow p-6">
    <p className="text-sm text-gray-600 mb-2">{title}</p>
    <p className="text-2xl font-bold">{value}</p>
    {growth !== undefined && (
      <p className={`text-sm ${growth >= 0 ? 'text-green-600' : 'text-red-600'}`}>
        {growth >= 0 ? '↑' : '↓'} {Math.abs(growth * 100).toFixed(1)}%
      </p>
    )}
  </div>
);

const StatusBadge = ({ status }: { status: string }) => {
  const colors: Record<string, string> = {
    CONFIRMED: 'bg-green-100 text-green-800',
    PENDING_PAYMENT: 'bg-yellow-100 text-yellow-800',
    COMPLETED: 'bg-blue-100 text-blue-800',
    CANCELLED: 'bg-red-100 text-red-800',
  };

  return (
    <span className={`px-2 py-1 rounded text-xs ${colors[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
};
```

---

## 2. Calendario de Citas (SCREEN-043)

### Descripción
Vista de calendario visual para gestionar citas por fecha y terapeuta.

### Endpoints Disponibles

#### 2.1 Listar Citas (con filtros)
```typescript
GET /api/v1/spa/appointments/
```

**Query Parameters:**
- `start_time__gte`: ISO DateTime (filtrar desde)
- `start_time__lte`: ISO DateTime (filtrar hasta)
- `staff_member`: UUID (filtrar por terapeuta)
- `status`: string (CONFIRMED, PENDING_PAYMENT, etc.)
- `page`: number
- `page_size`: number (default: 20)

**Response:**
```json
{
  "count": 45,
  "next": "http://api/spa/appointments/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "user": {
        "id": "uuid",
        "first_name": "María",
        "last_name": "García"
      },
      "services": [
        {
          "id": "uuid",
          "service": {
            "id": "uuid",
            "name": "Masaje Relajante",
            "duration": 60
          },
          "duration": 60,
          "price_at_purchase": 80000
        }
      ],
      "staff_member": {
        "id": "uuid",
        "first_name": "Andrea",
        "last_name": "Calma"
      },
      "start_time": "2025-12-14T10:00:00-05:00",
      "end_time": "2025-12-14T11:00:00-05:00",
      "status": "CONFIRMED",
      "status_display": "Confirmada",
      "price_at_purchase": 80000,
      "total_duration_minutes": 60,
      "reschedule_count": 0,
      "created_at": "2025-12-10T15:30:00Z",
      "updated_at": "2025-12-10T15:30:00Z"
    }
  ]
}
```

#### 2.2 Disponibilidad de Terapeutas
```typescript
GET /api/v1/spa/availability/blocks/
```

**Query Parameters:**
- `date`: YYYY-MM-DD (requerido)
- `service_ids`: UUID[] (requerido, puede ser múltiple)

**Response:**
```json
[
  {
    "start_time": "2025-12-14T09:00:00-05:00",
    "staff_id": "uuid",
    "staff_label": "Terapeuta 1"
  },
  {
    "start_time": "2025-12-14T09:30:00-05:00",
    "staff_id": "uuid",
    "staff_label": "Terapeuta 1"
  }
]
```

### Implementación Frontend

```typescript
// app/admin/calendar/page.tsx
'use client';

import { useState, useEffect } from 'react';
import api from '@/lib/axios';
import { Calendar } from '@/components/Calendar'; // Usar librería como react-big-calendar
import { StaffRoute } from '@/components/ProtectedRoute';

interface CalendarEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  resource: {
    appointmentId: string;
    clientName: string;
    staffName: string;
    status: string;
  };
}

export default function AppointmentCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [selectedStaff, setSelectedStaff] = useState<string | null>(null);

  useEffect(() => {
    fetchAppointments();
  }, [selectedDate, selectedStaff]);

  const fetchAppointments = async () => {
    try {
      // Obtener rango de la semana actual
      const startOfWeek = new Date(selectedDate);
      startOfWeek.setDate(selectedDate.getDate() - selectedDate.getDay());
      
      const endOfWeek = new Date(startOfWeek);
      endOfWeek.setDate(startOfWeek.getDate() + 6);

      const params: any = {
        start_time__gte: startOfWeek.toISOString(),
        start_time__lte: endOfWeek.toISOString(),
        page_size: 100,
      };

      if (selectedStaff) {
        params.staff_member = selectedStaff;
      }

      const response = await api.get('/spa/appointments/', { params });

      const calendarEvents: CalendarEvent[] = response.data.results.map((apt: any) => ({
        id: apt.id,
        title: `${apt.user.first_name} - ${apt.services[0]?.service.name || 'Cita'}`,
        start: new Date(apt.start_time),
        end: new Date(apt.end_time),
        resource: {
          appointmentId: apt.id,
          clientName: `${apt.user.first_name} ${apt.user.last_name}`,
          staffName: apt.staff_member 
            ? `${apt.staff_member.first_name} ${apt.staff_member.last_name}`
            : 'Sin asignar',
          status: apt.status,
        },
      }));

      setEvents(calendarEvents);
    } catch (error) {
      console.error('Error fetching appointments:', error);
    }
  };

  const handleEventClick = (event: CalendarEvent) => {
    // Navegar al detalle de la cita
    window.location.href = `/admin/appointments/${event.resource.appointmentId}`;
  };

  return (
    <StaffRoute>
      <div className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">Calendario de Citas</h1>
          
          {/* Filtro de Terapeuta */}
          <select
            value={selectedStaff || ''}
            onChange={(e) => setSelectedStaff(e.target.value || null)}
            className="border rounded px-4 py-2"
          >
            <option value="">Todos los terapeutas</option>
            {/* Cargar lista de terapeutas dinámicamente */}
          </select>
        </div>

        {/* Usar react-big-calendar o similar */}
        <div className="bg-white rounded-lg shadow p-6" style={{ height: '600px' }}>
          <Calendar
            events={events}
            onSelectEvent={handleEventClick}
            defaultView="week"
            views={['month', 'week', 'day']}
          />
        </div>
      </div>
    </StaffRoute>
  );
}
```

---

## 3. Lista de Citas (SCREEN-044 y SCREEN-045)

### Descripción
Vista tabular de todas las citas con opciones de búsqueda, filtrado y acciones (ver detalle, reagendar, cancelar, completar).

### Endpoints Disponibles

#### 3.1 Listar Citas (igual que calendario)
```typescript
GET /api/v1/spa/appointments/
```

#### 3.2 Detalle de Cita
```typescript
GET /api/v1/spa/appointments/{id}/
```

**Response:** (Mismo formato que el item de la lista)

#### 3.3 Reagendar Cita
```typescript
POST /api/v1/spa/appointments/{id}/reschedule/
```

**Request Body:**
```json
{
  "new_start_time": "2025-12-15T10:00:00-05:00"
}
```

**Response:**
```json
{
  "id": "uuid",
  "start_time": "2025-12-15T10:00:00-05:00",
  "end_time": "2025-12-15T11:00:00-05:00",
  "status": "RESCHEDULED",
  "reschedule_count": 1
}
```

#### 3.4 Cancelar Cita
```typescript
POST /api/v1/spa/appointments/{id}/cancel/
```

**Request Body:**
```json
{
  "cancellation_reason": "Cliente solicitó cancelación"
}
```

**Response:**
```json
{
  "id": "uuid",
  "status": "CANCELLED",
  "credit_generated": "80000" // Solo si aplica
}
```

#### 3.5 Completar Cita (Staff only)
```typescript
POST /api/v1/spa/appointments/{id}/mark_completed/
```

**Response:**
```json
{
  "id": "uuid",
  "status": "COMPLETED"
}
```

#### 3.6 Marcar como No Show (Staff only)
```typescript
POST /api/v1/spa/appointments/{id}/mark_as_no_show/
```

**Response:**
```json
{
  "id": "uuid",
  "status": "CANCELLED",
  "outcome": "NO_SHOW"
}
```

### Implementación Frontend

```typescript
// app/admin/appointments/page.tsx
'use client';

import { useState, useEffect } from 'react';
import api from '@/lib/axios';
import { StaffRoute } from '@/components/ProtectedRoute';

interface Appointment {
  id: string;
  user: { first_name: string; last_name: string };
  staff_member: { first_name: string; last_name: string } | null;
  start_time: string;
  status: string;
  status_display: string;
  price_at_purchase: number;
  services: Array<{
    service: { name: string };
  }>;
}

export default function AppointmentsList() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    status: '',
    search: '',
    date: '',
  });

  useEffect(() => {
    fetchAppointments();
  }, [filters]);

  const fetchAppointments = async () => {
    try {
      const params: any = { page_size: 50 };

      if (filters.status) params.status = filters.status;
      if (filters.date) {
        const date = new Date(filters.date);
        params.start_time__gte = date.toISOString();
        params.start_time__lte = new Date(date.setHours(23, 59, 59)).toISOString();
      }

      const response = await api.get('/spa/appointments/', { params });
      setAppointments(response.data.results);
    } catch (error) {
      console.error('Error fetching appointments:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async (id: string) => {
    if (!confirm('¿Marcar esta cita como completada?')) return;

    try {
      await api.post(`/spa/appointments/${id}/mark_completed/`);
      fetchAppointments(); // Refrescar lista
      alert('Cita completada exitosamente');
    } catch (error: any) {
      alert(error.response?.data?.error || 'Error al completar cita');
    }
  };

  const handleNoShow = async (id: string) => {
    if (!confirm('¿Marcar como No Show? Se generará crédito según política.')) return;

    try {
      await api.post(`/spa/appointments/${id}/mark_as_no_show/`);
      fetchAppointments();
      alert('Cita marcada como No Show');
    } catch (error: any) {
      alert(error.response?.data?.error || 'Error al marcar No Show');
    }
  };

  if (loading) return <div>Cargando...</div>;

  return (
    <StaffRoute>
      <div className="p-6">
        <h1 className="text-3xl font-bold mb-6">Gestión de Citas</h1>

        {/* Filtros */}
        <div className="bg-white rounded-lg shadow p-4 mb-6 flex gap-4">
          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="border rounded px-4 py-2"
          >
            <option value="">Todos los estados</option>
            <option value="CONFIRMED">Confirmadas</option>
            <option value="PENDING_PAYMENT">Pendiente de Pago</option>
            <option value="COMPLETED">Completadas</option>
            <option value="CANCELLED">Canceladas</option>
          </select>

          <input
            type="date"
            value={filters.date}
            onChange={(e) => setFilters({ ...filters, date: e.target.value })}
            className="border rounded px-4 py-2"
          />
        </div>

        {/* Tabla */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Cliente
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Terapeuta
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Fecha/Hora
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Servicios
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Estado
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {appointments.map((apt) => (
                <tr key={apt.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    {apt.user.first_name} {apt.user.last_name}
                  </td>
                  <td className="px-6 py-4">
                    {apt.staff_member
                      ? `${apt.staff_member.first_name} ${apt.staff_member.last_name}`
                      : 'Sin asignar'}
                  </td>
                  <td className="px-6 py-4">
                    {new Date(apt.start_time).toLocaleString('es-CO')}
                  </td>
                  <td className="px-6 py-4">
                    {apt.services.map((s) => s.service.name).join(', ')}
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={apt.status} />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => (window.location.href = `/admin/appointments/${apt.id}`)}
                        className="text-blue-600 hover:underline text-sm"
                      >
                        Ver
                      </button>
                      {apt.status === 'CONFIRMED' && (
                        <>
                          <button
                            onClick={() => handleComplete(apt.id)}
                            className="text-green-600 hover:underline text-sm"
                          >
                            Completar
                          </button>
                          <button
                            onClick={() => handleNoShow(apt.id)}
                            className="text-red-600 hover:underline text-sm"
                          >
                            No Show
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </StaffRoute>
  );
}

const StatusBadge = ({ status }: { status: string }) => {
  const colors: Record<string, string> = {
    CONFIRMED: 'bg-green-100 text-green-800',
    PENDING_PAYMENT: 'bg-yellow-100 text-yellow-800',
    COMPLETED: 'bg-blue-100 text-blue-800',
    CANCELLED: 'bg-red-100 text-red-800',
    RESCHEDULED: 'bg-purple-100 text-purple-800',
  };

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
};
```

---

## 📦 Tipos TypeScript

```typescript
// types/admin.ts

export interface User {
  id: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  role: 'CLIENT' | 'VIP' | 'STAFF' | 'ADMIN';
}

export interface Service {
  id: string;
  name: string;
  duration: number;
  price: number;
  vip_price: number | null;
}

export interface AppointmentItem {
  id: string;
  service: Service;
  duration: number;
  price_at_purchase: number;
}

export interface Appointment {
  id: string;
  user: User;
  staff_member: User | null;
  services: AppointmentItem[];
  start_time: string;
  end_time: string;
  status: 'PENDING_PAYMENT' | 'PAID' | 'CONFIRMED' | 'RESCHEDULED' | 'COMPLETED' | 'CANCELLED';
  status_display: string;
  price_at_purchase: number;
  total_duration_minutes: number;
  reschedule_count: number;
  created_at: string;
  updated_at: string;
}

export interface DashboardKPIs {
  total_revenue: number;
  total_appointments: number;
  avg_ticket: number;
  completion_rate: number;
  cancellation_rate: number;
  no_show_rate: number;
  new_clients: number;
  returning_clients: number;
  vip_clients: number;
  debt_recovery: {
    total_pending: number;
    recovered_this_period: number;
  };
  growth: {
    revenue_growth: number;
    appointments_growth: number;
  };
  start_date: string;
  end_date: string;
}

export interface AgendaItem {
  appointment_id: string;
  start_time: string;
  status: string;
  client: {
    id: string;
    name: string;
    phone: string;
    email: string;
  };
  staff: {
    id: string;
    name: string;
    phone: string;
    email: string;
  };
  has_debt: boolean;
}

export interface PendingPayment {
  type: 'payment' | 'appointment';
  payment_id?: string;
  appointment_id?: string;
  amount?: number;
  amount_due?: number;
  user: {
    id: string;
    name: string;
    phone: string;
    email: string;
  };
  created_at?: string;
  start_time?: string;
}
```

---

## 🎣 Hooks Reutilizables

```typescript
// hooks/useAppointments.ts
import { useState, useEffect } from 'react';
import api from '@/lib/axios';
import { Appointment } from '@/types/admin';

interface UseAppointmentsOptions {
  status?: string;
  staffId?: string;
  startDate?: string;
  endDate?: string;
  autoFetch?: boolean;
}

export const useAppointments = (options: UseAppointmentsOptions = {}) => {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAppointments = async () => {
    setLoading(true);
    setError(null);

    try {
      const params: any = { page_size: 100 };

      if (options.status) params.status = options.status;
      if (options.staffId) params.staff_member = options.staffId;
      if (options.startDate) params.start_time__gte = options.startDate;
      if (options.endDate) params.start_time__lte = options.endDate;

      const response = await api.get('/spa/appointments/', { params });
      setAppointments(response.data.results);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al cargar citas');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (options.autoFetch !== false) {
      fetchAppointments();
    }
  }, [options.status, options.staffId, options.startDate, options.endDate]);

  const completeAppointment = async (id: string) => {
    await api.post(`/spa/appointments/${id}/mark_completed/`);
    await fetchAppointments();
  };

  const markNoShow = async (id: string) => {
    await api.post(`/spa/appointments/${id}/mark_as_no_show/`);
    await fetchAppointments();
  };

  const cancelAppointment = async (id: string, reason: string) => {
    await api.post(`/spa/appointments/${id}/cancel/`, {
      cancellation_reason: reason,
    });
    await fetchAppointments();
  };

  return {
    appointments,
    loading,
    error,
    fetchAppointments,
    completeAppointment,
    markNoShow,
    cancelAppointment,
  };
};
```

```typescript
// hooks/useDashboard.ts
import { useState, useEffect } from 'react';
import api from '@/lib/axios';
import { DashboardKPIs, AgendaItem, PendingPayment } from '@/types/admin';

export const useDashboard = () => {
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [pendingPayments, setPendingPayments] = useState<PendingPayment[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDashboard = async () => {
    setLoading(true);

    try {
      const today = new Date().toISOString().split('T')[0];

      const [kpisRes, agendaRes, paymentsRes] = await Promise.all([
        api.get('/analytics/kpis/', {
          params: { start_date: today, end_date: today },
        }),
        api.get('/analytics/dashboard/agenda-today/'),
        api.get('/analytics/dashboard/pending-payments/'),
      ]);

      setKpis(kpisRes.data);
      setAgenda(agendaRes.data.results);
      setPendingPayments(paymentsRes.data.results);
    } catch (error) {
      console.error('Error fetching dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  return {
    kpis,
    agenda,
    pendingPayments,
    loading,
    refetch: fetchDashboard,
  };
};
```

---

## 🔄 Manejo de Errores

```typescript
// utils/errorHandler.ts
import { AxiosError } from 'axios';

export const handleApiError = (error: unknown): string => {
  if (error instanceof AxiosError) {
    // Error de negocio con código interno
    if (error.response?.data?.internal_code) {
      const code = error.response.data.internal_code;
      const errorMessages: Record<string, string> = {
        'APP-001': 'El horario ya no está disponible',
        'APP-002': 'El terapeuta no trabaja en este horario',
        'APP-003': 'Has alcanzado el límite de citas activas',
        'APP-004': 'Tienes un pago pendiente. Complétalo antes de agendar',
        'APP-005': 'Servicio duplicado en la solicitud',
      };

      return errorMessages[code] || error.response.data.detail;
    }

    // Error genérico del backend
    if (error.response?.data?.error) {
      return error.response.data.error;
    }

    // Error de red
    if (!error.response) {
      return 'Error de conexión. Verifica tu internet';
    }

    return 'Error inesperado. Intenta de nuevo';
  }

  return 'Error desconocido';
};
```

---

## 📝 Notas Importantes

### Caché
- Los endpoints de analytics usan caché con TTL dinámico (5 min - 2 horas)
- Usa `?force_refresh=true` en `/analytics/kpis/` para invalidar caché
- El endpoint `/analytics/cache/clear/` permite limpiar caché manualmente

### Permisos
- **Dashboard**: Requiere `CanViewAnalytics` (STAFF o ADMIN)
- **KPIs Financieros**: Requiere `CanViewFinancialMetrics` (solo ADMIN)
- **Completar/No Show**: Requiere `IsStaffOrAdmin`

### Paginación
- Usa `page_size` para controlar resultados por página (default: 20, max: 100)
- Los endpoints de dashboard tienen paginación de 50 items

### Fechas
- Todas las fechas en formato ISO 8601
- El backend usa timezone `America/Bogota`
- Convertir a local en frontend con `toLocaleString('es-CO')`

---

## 🚀 Próximos Pasos

1. Implementar las 3 pantallas base (Dashboard, Calendario, Lista)
2. Agregar tests unitarios para hooks
3. Implementar manejo de errores robusto
4. Agregar loading states y skeletons
5. Implementar búsqueda en tiempo real (debounced)
6. Agregar exportación de reportes (CSV/Excel)
