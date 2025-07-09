from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from spa.models import StaffAvailability
import datetime

CustomUser = get_user_model()


@receiver(post_save, sender=CustomUser)
def create_default_staff_availability(sender, instance, created, **kwargs):
    """
    Señal que se activa después de guardar un CustomUser.
    Si el usuario es nuevo y es STAFF, se crea su horario por defecto.
    """
    if created and instance.role == CustomUser.Role.STAFF:
        # Horarios por defecto
        morning_start = datetime.time(8, 0)
        morning_end = datetime.time(13, 0)
        afternoon_start = datetime.time(14, 0)
        afternoon_end = datetime.time(19, 0)

        # CORRECCIÓN: Iterar de Lunes (1) a Sábado (6).
        # El rango correcto es range(1, 7) para generar los números del 1 al 6.
        for day in range(1, 7):
            StaffAvailability.objects.create(
                staff_member=instance,
                day_of_week=day,
                start_time=morning_start,
                end_time=morning_end
            )
            StaffAvailability.objects.create(
                staff_member=instance,
                day_of_week=day,
                start_time=afternoon_start,
                end_time=afternoon_end
            )
        print(
            f"Horario por defecto creado para el nuevo miembro del staff: {instance.phone_number}")