from datetime import datetime, timedelta
from django.utils import timezone
from .models import Service, StaffAvailability, Appointment
from core.models import GlobalSettings

def calculate_available_slots(service_id: str, selected_date: datetime.date):
    """
    Servicio centralizado para calcular los horarios de citas disponibles para un
    servicio y una fecha específicos.

    Esta función encapsula toda la lógica de negocio:
    - Horarios de trabajo del personal.
    - Citas ya agendadas.
    - Tiempo de búfer/limpieza entre citas.

    Args:
        service_id: El ID del servicio para el cual se calcula la disponibilidad.
        selected_date: La fecha para la cual se calcula la disponibilidad.

    Returns:
        Un diccionario de horarios disponibles, agrupados por hora.
    """
    try:
        service = Service.objects.get(id=service_id, is_active=True)
    except Service.DoesNotExist:
        # Devuelve un diccionario vacío si el servicio no es válido
        return {}

    settings = GlobalSettings.load()
    buffer_time = timedelta(minutes=settings.appointment_buffer_time)
    service_duration = timedelta(minutes=service.duration)
    day_of_week = selected_date.isoweekday()

    # Obtener todas las disponibilidades y citas para ese día para optimizar consultas
    all_availabilities = StaffAvailability.objects.filter(day_of_week=day_of_week).select_related('staff_member')
    booked_appointments = Appointment.objects.filter(
        start_time__date=selected_date,
        status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PENDING_ADVANCE]
    )

    slots = {}
    for availability in all_availabilities:
        staff = availability.staff_member
        
        # Usamos timezone.make_aware para crear objetos datetime localizados correctamente
        slot_time = timezone.make_aware(datetime.combine(selected_date, availability.start_time))
        schedule_end_time = timezone.make_aware(datetime.combine(selected_date, availability.end_time))

        while slot_time + service_duration <= schedule_end_time:
            slot_end = slot_time + service_duration

            is_booked = booked_appointments.filter(
                staff_member=staff,
                start_time__lt=slot_end + buffer_time,
                end_time__gt=slot_time - buffer_time
            ).exists()

            if not is_booked:
                time_str = slot_time.strftime('%H:%M')
                if time_str not in slots:
                    slots[time_str] = []
                
                slots[time_str].append({
                    "staff_id": staff.id,
                    "staff_name": f"{staff.first_name} {staff.last_name}"
                })
            
            slot_time += timedelta(minutes=15)

    return dict(sorted(slots.items()))