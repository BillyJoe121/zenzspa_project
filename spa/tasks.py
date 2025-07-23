import logging
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from datetime import timedelta
from .models import Appointment

# Se obtiene una instancia del logger.
# __name__ asegura que el logger se nombre según el módulo (ej. 'spa.tasks')
logger = logging.getLogger(__name__)

@shared_task
def send_appointment_reminder(appointment_id):
    """
    Tarea de Celery que busca una cita y envía un recordatorio por EMAIL.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        if not appointment.user.email:
            logger.warning(f"Recordatorio no enviado para cita {appointment_id}: el usuario no tiene email.")
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
        
        logger.info(f"Recordatorio por email procesado y enviado para la cita {appointment_id}")
        return f"Recordatorio por email procesado para la cita {appointment_id}"
    except Appointment.DoesNotExist:
        logger.error(f"Error al procesar recordatorio: Cita con id={appointment_id} no encontrada.")
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
    
    count = appointments_to_remind.count()
    if count > 0:
        logger.info(f"Verificando recordatorios: {count} citas encontradas para recordar.")
    
    for appt in appointments_to_remind:
        send_appointment_reminder.delay(appt.id)
    
    return f"Verificación completada. {count} recordatorios encolados."


@shared_task
def cancel_unpaid_appointments():
    """
    Tarea de Celery para cancelar citas cuyo anticipo no ha sido pagado después de un tiempo configurable.
    """
    # El umbral es de 20 minutos, según el nuevo requerimiento.
    time_threshold = timezone.now() - timedelta(minutes=20)
    
    unpaid_appointments = Appointment.objects.filter(
        status=Appointment.AppointmentStatus.PENDING_ADVANCE,
        created_at__lt=time_threshold
    )
    
    if not unpaid_appointments.exists():
        # Si no hay citas que cancelar, la tarea termina sin hacer nada.
        return "No hay citas pendientes de pago para cancelar."
        
    # Se itera sobre las citas para poder loggear cada una individualmente.
    cancelled_count = 0
    for appt in unpaid_appointments:
        appt.status = Appointment.AppointmentStatus.CANCELLED_BY_SYSTEM
        appt.save(update_fields=['status'])
        
        # Se añade el logging para cada cita cancelada.
        logger.info(
            f"Cita ID {appt.id} para el usuario {appt.user.email} ha sido cancelada "
            f"automáticamente por falta de pago del anticipo."
        )
        cancelled_count += 1
    
    if cancelled_count > 0:
        logger.info(f"Tarea finalizada: {cancelled_count} citas pendientes de anticipo han sido canceladas por el sistema.")
        # Aquí se podría encolar otra tarea para notificar a los usuarios de la cancelación.
        
    return f"{cancelled_count} citas pendientes de anticipo han sido canceladas."