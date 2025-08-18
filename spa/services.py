from datetime import datetime, timedelta
from django.utils import timezone
from .models import Service, StaffAvailability, Appointment
from core.models import GlobalSettings
from django.db import transaction
from .models import Payment, UserPackage, Voucher, Package, ClientCredit
from users.models import CustomUser
from django.db.models import Q
import hashlib
import json
from django.conf import settings
from decimal import Decimal

class AppointmentService:
    """
    Servicio para manejar la lógica de negocio de la creación de citas.
    Centraliza la validación y la creación para prevenir condiciones de carrera.
    """
    def __init__(self, user, service, staff_member, start_time):
        self.user = user
        self.service = service
        self.staff_member = staff_member
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=service.duration)

    def _validate_appointment_rules(self):
        """Validaciones de reglas de negocio que no requieren bloqueo de BD."""
        if self.start_time < timezone.now():
            raise ValueError("No se puede reservar una cita en el pasado.")

        if self.user.has_pending_final_payment():
            raise ValueError("No puedes agendar una nueva cita porque tienes un pago final pendiente.")

        active_appointments = Appointment.objects.filter(
            user=self.user,
            status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PENDING_ADVANCE]
        ).count()

        if self.user.role == CustomUser.Role.CLIENT and active_appointments >= 1:
            raise ValueError("Como CLIENTE, solo puedes tener 1 cita activa.")
        if self.user.role == CustomUser.Role.VIP and active_appointments >= 4:
            raise ValueError("Como VIP, puedes tener hasta 4 citas activas.")

    @transaction.atomic
    def create_appointment_with_lock(self):
        self._validate_appointment_rules()
        buffer_time = timedelta(minutes=GlobalSettings.load().appointment_buffer_time)
        conflicting_appointments = Appointment.objects.select_for_update().filter(
            staff_member=self.staff_member,
            status__in=[Appointment.AppointmentStatus.CONFIRMED, Appointment.AppointmentStatus.PENDING_ADVANCE],
            start_time__lt=self.end_time + buffer_time,
            end_time__gt=self.start_time - buffer_time
        ).exists()
        if conflicting_appointments:
            raise ValueError("El horario seleccionado ya no está disponible.")

        price = self.service.vip_price if self.user.role == CustomUser.Role.VIP and self.service.vip_price is not None else self.service.price
        
        appointment = Appointment.objects.create(
            user=self.user,
            service=self.service,
            staff_member=self.staff_member,
            start_time=self.start_time,
            end_time=self.end_time,
            price_at_purchase=price,
            status=Appointment.AppointmentStatus.PENDING_ADVANCE # Estado inicial
        )

        # --- INICIO DE LA MODIFICACIÓN ---
        # Se delega la creación del pago al nuevo PaymentService
        payment_service = PaymentService(user=self.user)
        payment_service.create_advance_payment_for_appointment(appointment)
        # --- FIN DE LA MODIFICACIÓN ---

        return appointment


def calculate_available_slots(service_id: str, selected_date: datetime.date):

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

class WompiWebhookService:
    """
    Servicio para procesar y validar webhooks de Wompi.
    """
    def __init__(self, request_data):
        self.data = request_data.get("data", {})
        self.event_type = request_data.get("event")
        self.sent_signature = request_data.get("signature", {}).get("checksum")
        self.timestamp = request_data.get("timestamp")

    def _validate_signature(self):
        """
        Valida la firma del evento para asegurar que proviene de Wompi.
        """
        if not all([self.data, self.sent_signature, self.timestamp]):
            raise ValueError("Firma o datos del webhook incompletos.")
        
        # El cuerpo del evento (data) debe ser convertido a un string JSON compacto.
        event_body_str = json.dumps(self.data, separators=(',', ':'))
        
        # La cadena a firmar es: body + timestamp + secreto_de_eventos
        # Asegúrate de tener WOMPI_EVENTS_SECRET en tu settings.py
        concatenation = f"{event_body_str}{self.timestamp}{settings.WOMPI_EVENTS_SECRET}"
        
        calculated_signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()
        
        if not hashlib.sha256(self.sent_signature.encode('utf-8')).hexdigest() == hashlib.sha256(calculated_signature.encode('utf-8')).hexdigest():
            raise ValueError("Firma del webhook inválida. La petición podría ser fraudulenta.")

    @transaction.atomic
    def process_transaction_update(self):
        """
        Procesa un evento 'transaction.updated'.
        Es idempotente y seguro.
        """
        # 1. Validar la firma antes de tocar la base de datos.
        self._validate_signature()

        transaction_data = self.data.get("transaction", {})
        reference = transaction_data.get("reference")
        transaction_status = transaction_data.get("status")

        if not reference or not transaction_status:
            raise ValueError("Referencia o estado de la transacción ausentes en el webhook.")
        
        # 2. Obtener y bloquear el pago para asegurar la atomicidad e idempotencia.
        try:
            # Clave de la idempotencia: solo buscamos pagos que aún están PENDIENTES.
            payment = Payment.objects.select_for_update().get(transaction_id=reference, status=Payment.PaymentStatus.PENDING)
        except Payment.DoesNotExist:
            # Si no encontramos un pago PENDIENTE, significa que ya fue procesado
            # o que la referencia es inválida. En ambos casos, no hacemos nada.
            return {"status": "already_processed_or_invalid"}

        # 3. Actualizar el pago con los datos de Wompi.
        payment.status = transaction_status
        payment.raw_response = transaction_data # Guardar la respuesta completa para auditoría

        if transaction_status == 'APPROVED':
            # Es importante actualizar el transaction_id con el definitivo de Wompi
            payment.transaction_id = transaction_data.get("id", payment.transaction_id)
            payment.save()
            
            # 4. Disparar la lógica de negocio correspondiente (otorgar servicios).
            if payment.payment_type == Payment.PaymentType.PACKAGE:
                PackagePurchaseService.fulfill_purchase(payment)
            elif payment.payment_type == Payment.PaymentType.ADVANCE:
                if payment.appointment:
                    payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                    payment.appointment.save(update_fields=['status'])
            elif payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION:
                VipSubscriptionService.fulfill_subscription(payment)
        else:
            # Si el estado es (DECLINED, VOIDED, ERROR), solo guardamos el estado.
            payment.save()
            
        return {"status": "processed_successfully", "payment_id": payment.id}

class PaymentService:
    """
    Servicio para manejar la lógica de negocio de los pagos,
    incluyendo la aplicación de saldo a favor (ClientCredit).
    """
    def __init__(self, user):
        self.user = user

    @transaction.atomic
    def create_advance_payment_for_appointment(self, appointment: Appointment):
        """
        Crea el registro de pago de anticipo para una cita, aplicando
        el saldo a favor disponible del usuario si existe.
        """
        settings = GlobalSettings.load()
        price = appointment.price_at_purchase
        advance_percentage = Decimal(settings.advance_payment_percentage / 100)
        required_advance = price * advance_percentage

        # Buscar créditos válidos (disponibles, no expirados) del usuario
        available_credits = ClientCredit.objects.select_for_update().filter(
            user=self.user,
            status__in=[ClientCredit.CreditStatus.AVAILABLE, ClientCredit.CreditStatus.PARTIALLY_USED],
            expires_at__gte=timezone.now().date()
        ).order_by('created_at') # Usar los créditos más antiguos primero

        amount_to_pay = required_advance
        credit_used = None

        for credit in available_credits:
            if amount_to_pay <= 0:
                break
            
            amount_from_this_credit = min(amount_to_pay, credit.remaining_amount)
            
            credit.remaining_amount -= amount_from_this_credit
            credit.save()
            
            amount_to_pay -= amount_from_this_credit
            credit_used = credit # Guardamos la referencia al último crédito usado
        
        # Crear el registro de pago
        payment = Payment.objects.create(
            user=self.user,
            appointment=appointment,
            amount=required_advance,
            payment_type=Payment.PaymentType.ADVANCE,
            used_credit=credit_used
        )

        if amount_to_pay <= 0:
            # El crédito cubrió todo el anticipo. La cita se confirma automáticamente.
            payment.status = Payment.PaymentStatus.PAID_WITH_CREDIT
            appointment.status = Appointment.AppointmentStatus.CONFIRMED
        else:
            # Queda un remanente por pagar. La cita queda pendiente.
            payment.status = Payment.PaymentStatus.PENDING
            # Actualizamos el monto del pago al remanente, para que la pasarela
            # solo cobre lo que falta.
            payment.amount = amount_to_pay

        payment.save()
        appointment.save(update_fields=['status'])
        
        return payment
    

