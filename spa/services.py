from datetime import datetime, timedelta
from django.utils import timezone
from .models import Service, StaffAvailability, Appointment
from core.models import GlobalSettings
from django.db import transaction
from .models import Payment, UserPackage, Voucher, Package
from users.models import CustomUser


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

class PackagePurchaseService:
    """
    Servicio para manejar la lógica de negocio de la compra de paquetes.
    """
    @staticmethod
    @transaction.atomic
    def fulfill_purchase(payment: Payment):
        """
        Crea el UserPackage y los Vouchers asociados después de un pago exitoso.
        Este método es idempotente; no hará nada si el paquete ya fue otorgado.
        
        Args:
            payment (Payment): La instancia del pago aprobado.
        """
        # Extraer el ID del paquete de la referencia del pago. Ej: 'PACKAGE-uuid'
        try:
            package_id = payment.transaction_id.split('-')[1]
            package = Package.objects.get(id=package_id)
        except (IndexError, Package.DoesNotExist):
            # Loggear un error aquí sería ideal en un entorno de producción.
            # No se puede procesar si el paquete no existe.
            return

        # Verificar si este pago ya procesó una compra para evitar duplicados.
        if hasattr(payment, 'user_package_purchase'):
            return

        # 1. Crear el registro de la compra (UserPackage)
        user_package = UserPackage.objects.create(
            user=payment.user,
            package=package,
            payment=payment
            # La fecha de expiración se calcula automáticamente en el método save() del modelo.
        )

        # 2. Generar los vouchers para cada servicio en el paquete
        # Usamos `packageservice_set` que definimos en el related_name a través de la tabla intermedia.
        for package_service in package.packageservice_set.all():
            for _ in range(package_service.quantity):
                Voucher.objects.create(
                    user_package=user_package,
                    user=payment.user,
                    service=package_service.service
                )

        return user_package
    
class VipSubscriptionService:
    """
    Servicio para manejar la lógica de negocio de las suscripciones VIP.
    """
    @staticmethod
    @transaction.atomic
    def fulfill_subscription(payment: Payment):
        """
        Activa o extiende la membresía VIP de un usuario después de un pago exitoso.
        Este método es el corazón de la activación de beneficios.

        Args:
            payment (Payment): La instancia del pago de suscripción aprobado.
        """
        user = payment.user
        
        # 1. Determinar la fecha de inicio de la nueva suscripción
        # Si el usuario ya es un VIP activo, la nueva suscripción empieza
        # el día que termina la actual (renovación). Si no, empieza hoy.
        today = timezone.now().date()
        start_date = today
        if user.is_vip and user.vip_expires_at > today:
            start_date = user.vip_expires_at + timedelta(days=1)
        
        # 2. Calcular la nueva fecha de vencimiento (30 días de membresía)
        end_date = start_date + timedelta(days=30)

        # 3. Actualizar el perfil del usuario
        user.role = CustomUser.Role.VIP
        user.vip_expires_at = end_date
        user.save(update_fields=['role', 'vip_expires_at'])

        # 4. Crear un registro en el log para auditoría
        SubscriptionLog.objects.create(
            user=user,
            payment=payment,
            start_date=start_date,
            end_date=end_date
        )
