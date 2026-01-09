import os, sys
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')

import django
django.setup()

from django.utils import timezone
from datetime import timedelta
from spa.models import Appointment
from spa.services.appointments import AppointmentService
from users.models import CustomUser

APPOINTMENT_ID = '69869c3f-9627-4486-bb25-d1cc4dd54bfb'

# Obtener la cita
appointment = Appointment.objects.get(id=APPOINTMENT_ID)
print(f'Cita actual: {appointment.id}')
print(f'  Fecha actual: {appointment.start_time}')
print(f'  Status: {appointment.status}')

# Obtener el usuario (admin) para el acting_user
user = appointment.user
print(f'  Usuario: {user.phone_number}')

# Nueva hora: hoy 21:15 (9:15 PM Colombia = 02:15 UTC mañana)
now = timezone.now()
# 21:15 hora Colombia = UTC - 5 = 02:15 UTC del día siguiente
# Pero necesitamos calcularlo bien
colombia_offset = timedelta(hours=-5)
target_local = now.replace(hour=21, minute=15, second=0, microsecond=0)
# Ajustar si ya pasó esa hora hoy
if target_local <= now:
    target_local = target_local + timedelta(days=1)

new_start_time = target_local

print(f'')
print(f'Reagendando a: {new_start_time}')
print(f'  (Hora Colombia: 21:15)')

# Reagendar usando el servicio
try:
    updated = AppointmentService.reschedule_appointment(
        appointment=appointment,
        new_start_time=new_start_time,
        acting_user=user,
        skip_counter=True  # No contar como reagendamiento del cliente
    )
    print(f'')
    print(f'EXITO! Cita reagendada:')
    print(f'  Nueva fecha: {updated.start_time}')
    print(f'  Status: {updated.status}')
    print(f'  Contador reschedule: {updated.reschedule_count}')
    print(f'')
    print(f'El recordatorio de 2h deberia llegar a las ~19:15')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
