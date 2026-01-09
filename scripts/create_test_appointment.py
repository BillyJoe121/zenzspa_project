import os
import sys
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')

import django
django.setup()

from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import CustomUser
from spa.models import Appointment, Service, AppointmentItem

TEST_PHONE = '+573157589548'

# 1. Obtener usuario existente (NO modificar rol)
try:
    user = CustomUser.objects.get(phone_number=TEST_PHONE)
    print(f'Usuario encontrado: {user.phone_number}')
    print(f'   Rol: {user.role} (NO modificado)')
    print(f'   Nombre: {user.get_full_name()}')
except CustomUser.DoesNotExist:
    print('ERROR: Usuario no encontrado')
    exit(1)

# 2. Obtener un servicio existente
service = Service.objects.filter(is_active=True).first()
print(f'Servicio: {service.name} ({service.duration} min)')

# 3. Crear cita para manana 19:30
now = timezone.now()
start_time = now.replace(hour=19, minute=30, second=0, microsecond=0) + timedelta(days=1)
end_time = start_time + timedelta(minutes=service.duration)

print(f'Hora actual: {now}')
print(f'Cita programada para: {start_time}')

# Cancelar citas confirmadas anteriores de este usuario
cancelled = Appointment.objects.filter(
    user=user,
    status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.RESCHEDULED]
).update(status=Appointment.AppointmentStatus.CANCELLED)
if cancelled:
    print(f'Canceladas {cancelled} citas anteriores')

# Crear la nueva cita
appointment = Appointment.objects.create(
    user=user,
    start_time=start_time,
    end_time=end_time,
    status=Appointment.AppointmentStatus.CONFIRMED,
    price_at_purchase=service.price,
)

AppointmentItem.objects.create(
    appointment=appointment,
    service=service,
    duration=service.duration,
    price_at_purchase=service.price,
)

print('')
print('CITA CREADA:')
print(f'   ID: {appointment.id}')
print(f'   Fecha: {start_time}')
print(f'   Status: {appointment.status}')
print(f'   Servicios: {appointment.get_service_names()}')
print('')
print('El recordatorio 24h se enviara a las 19:00 de hoy')
