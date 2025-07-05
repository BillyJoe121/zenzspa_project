from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from .models import CustomUser


@shared_task
def send_non_grata_alert_to_admins(phone_number):
    """
    Notifica a todos los administradores sobre un intento de registro
    de un número de teléfono marcado como 'No Grato'.
    """
    admin_emails = CustomUser.objects.filter(
        role=CustomUser.Role.ADMIN,
        is_active=True
    ).values_list('email', flat=True)

    if not admin_emails:
        print(
            "ALERTA 'NO GRATO': No se encontraron administradores activos para notificar.")
        return

    subject = '[ZenzSpa Alerta de Seguridad] Intento de Registro Bloqueado'
    message = (
        f'Se ha detectado y bloqueado un intento de registro utilizando el número de teléfono: {phone_number}.\n\n'
        f'Este número pertenece a un usuario previamente marcado como "Persona Non Grata" en el sistema.\n\n'
        f'Atentamente,\nEl Sistema de Vigilancia de ZenzSpa'
    )
    from_email = settings.DEFAULT_FROM_EMAIL

    # En desarrollo, esto imprimirá en la consola si tienes configurado el EmailBackend de consola.
    # En producción, enviará un email real.
    send_mail(subject, message, from_email, list(admin_emails))

    print(
        f"ALERTA 'NO GRATO': Notificación enviada a los administradores sobre el número {phone_number}.")

    return f"Notificación enviada para el número {phone_number}"
