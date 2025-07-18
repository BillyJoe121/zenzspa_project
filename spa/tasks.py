from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from datetime import timedelta
from .models import Appointment


@shared_task
def send_appointment_reminder(appointment_id):
    """
    Tarea de Celery que busca una cita y envía un recordatorio por EMAIL.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        if not appointment.user.email:
            return f"Recordatorio no enviado para cita {appointment_id}: el usuario no tiene email."

        subject = f"Recordatorio de tu cita en ZenzSpa - Mañana"
        start_time_local = appointment.start_time.astimezone(timezone.get_current_timezone())
        message = (
            f"Hola {appointment.user.first_name},\n\n"
            f"Este es un recordatorio de tu cita en ZenzSpa para el servicio '{appointment.service.name}'.\n"
            f"Tu cita es mañana, {start_time_local.strftime('%d de %B')} a las {start_time_local.strftime('%I:%M %p')}.\n\n"
            f"¡Te esperamos!\n\n"
            f"El equipo de ZenzSpa"
        )
        
        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[appointment.user.email],
            fail_silently=False,
        )
        
        print(f"--- [RECORDATORIO POR EMAIL PROCESADO] para la cita {appointment_id} ---")
        return f"Recordatorio por email procesado para la cita {appointment_id}"
    except Appointment.DoesNotExist:
        return f"No se procesó recordatorio: Cita con id={appointment_id} no encontrada."


@shared_task
def check_and_queue_reminders():
    """
    Tarea que se ejecuta periódicamente para buscar citas que necesiten recordatorio.
    """
    now = timezone.now()
    reminder_start_time = now + timedelta(hours=24)
    reminder_end_time = now + timedelta(hours=25)

    appointments_to_remind = Appointment.objects.filter(
        start_time__range=(reminder_start_time, reminder_end_time),
        status=Appointment.AppointmentStatus.CONFIRMED
    )
    
    print(f"--- [CELERY BEAT] Verificando recordatorios. {appointments_to_remind.count()} citas encontradas para recordar. ---")
    
    for appt in appointments_to_remind:
        send_appointment_reminder.delay(appt.id)
    
    return f"Verificación completada. {appointments_to_remind.count()} recordatorios encolados."

# --- INICIO DE LA MODIFICACIÓN ---

@shared_task
def cancel_unpaid_appointments():
    """
    Tarea de Celery para cancelar citas cuyo anticipo no ha sido pagado después de 20 minutos.
    """
    # El umbral es de 20 minutos, según el nuevo requerimiento.
    time_threshold = timezone.now() - timedelta(minutes=20)
    
    unpaid_appointments = Appointment.objects.filter(
        status=Appointment.AppointmentStatus.PENDING_ADVANCE,
        created_at__lt=time_threshold
    )
    
    count = unpaid_appointments.count()
    if count > 0:
        # Se cambia el estado al nuevo 'CANCELLED_BY_SYSTEM'
        unpaid_appointments.update(status=Appointment.AppointmentStatus.CANCELLED_BY_SYSTEM)
        print(f"--- [CELERY BEAT] {count} citas pendientes de anticipo han sido canceladas por el sistema. ---")
        # Aquí se podría encolar otra tarea para notificar a los usuarios de la cancelación.
        
    return f"{count} citas pendientes de anticipo han sido canceladas."
# --- FIN DE LA MODIFICACIÓN ---