# zenzspa_project/spa/tasks.py
from celery import shared_task
from django.utils import timezone
# <-- 1. Importar la función para enviar correos
from django.core.mail import send_mail
# Para plantillas HTML (opcional pero recomendado)
from django.template.loader import render_to_string
import datetime
from .models import Appointment


@shared_task
def send_appointment_reminder(appointment_id):
    """
    Tarea de Celery que busca una cita y envía un recordatorio por EMAIL.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)

        # --- 2. Lógica de envío de correo ---

        # Asegurarnos de que el usuario tiene un email
        if not appointment.user.email:
            return f"Recordatorio no enviado para cita {appointment_id}: el usuario no tiene email."

        # Asunto del correo
        subject = f"Recordatorio de tu cita en ZenzSpa - Mañana"

        # Cuerpo del mensaje (texto plano)
        start_time_local = appointment.start_time.astimezone(
            timezone.get_current_timezone())
        message = (
            f"Hola {appointment.user.first_name},\n\n"
            f"Este es un recordatorio de tu cita en ZenzSpa para el servicio '{appointment.service.name}'.\n"
            f"Tu cita es mañana, {start_time_local.strftime('%d de %B')} a las {start_time_local.strftime('%I:%M %p')}.\n\n"
            f"¡Te esperamos!\n\n"
            f"El equipo de ZenzSpa"
        )

        # Enviar el correo
        send_mail(
            subject=subject,
            message=message,
            from_email=None,  # Usará DEFAULT_FROM_EMAIL de settings.py
            recipient_list=[appointment.user.email],
            fail_silently=False,  # Si falla, queremos que la tarea de Celery muestre un error
        )

        print(
            f"--- [RECORDATORIO POR EMAIL PROCESADO] para la cita {appointment_id} ---")
        return f"Recordatorio por email procesado para la cita {appointment_id}"

    except Appointment.DoesNotExist:
        return f"No se procesó recordatorio: Cita con id={appointment_id} no encontrada."


@shared_task
def check_and_queue_reminders():
    """
    Tarea que se ejecuta periódicamente para buscar citas que necesiten recordatorio.
    (Esta tarea no cambia)
    """
    now = timezone.now()
    reminder_start_time = now + datetime.timedelta(hours=4)
    reminder_end_time = now + datetime.timedelta(hours=25)

    appointments_to_remind = Appointment.objects.filter(
        start_time__gte=reminder_start_time,
        start_time__lt=reminder_end_time,
        status=Appointment.AppointmentStatus.CONFIRMED
    )

    print(
        f"--- [CELERY BEAT] Verificando recordatorios. {appointments_to_remind.count()} citas encontradas para recordar. ---")

    for appt in appointments_to_remind:
        send_appointment_reminder.delay(appt.id)

    return f"Verificación completada. {appointments_to_remind.count()} recordatorios encolados."
