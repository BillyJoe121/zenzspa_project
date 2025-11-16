from collections import defaultdict
from datetime import datetime, timedelta
import logging
import uuid

from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
import hashlib
import json
from django.conf import settings
from decimal import Decimal
import requests

from marketplace.models import Order
from .models import (
    AvailabilityExclusion,
    Service,
    StaffAvailability,
    Appointment,
    AppointmentItem,
    WaitlistEntry,
    Payment,
    UserPackage,
    Voucher,
    Package,
    ClientCredit,
    SubscriptionLog,
    FinancialAdjustment,
    WebhookEvent,
    LoyaltyRewardLog,
)
from core.models import GlobalSettings, AuditLog
from users.models import CustomUser


logger = logging.getLogger(__name__)

class AvailabilityService:
    """
    Calcula slots disponibles considerando múltiples servicios y buffer.
    """

    BUFFER_MINUTES = 15
    SLOT_INTERVAL_MINUTES = 15

    def __init__(self, date, services):
        if not services:
            raise ValueError("Debes seleccionar al menos un servicio.")
        self.date = date
        self.services = list(services)
        self.buffer = timedelta(minutes=self.BUFFER_MINUTES)
        self.slot_interval = timedelta(minutes=self.SLOT_INTERVAL_MINUTES)
        self.service_duration = timedelta(
            minutes=sum(service.duration for service in self.services)
        )
        if self.service_duration <= timedelta(0):
            raise ValueError("Los servicios seleccionados no tienen duración válida.")

    @classmethod
    def for_service_ids(cls, date, service_ids):
        services = list(Service.objects.filter(id__in=service_ids, is_active=True))
        if len(services) != len(set(service_ids)):
            raise ValueError("Uno o más servicios seleccionados no existen o están inactivos.")
        return cls(date, services)

    @classmethod
    def get_available_slots(cls, date, service_ids, staff_member_id=None):
        instance = cls.for_service_ids(date, service_ids)
        return instance._build_slots(staff_member_id=staff_member_id)

    def total_price_for_user(self, user):
        total = Decimal('0')
        for service in self.services:
            if user and getattr(user, "is_vip", False) and service.vip_price:
                total += service.vip_price
            else:
                total += service.price
        return total

    def _build_slots(self, staff_member_id=None):
        day_of_week = self.date.isoweekday()
        availabilities = StaffAvailability.objects.filter(day_of_week=day_of_week)
        if staff_member_id:
            availabilities = availabilities.filter(staff_member_id=staff_member_id)
        availabilities = list(availabilities.select_related('staff_member'))
        staff_ids = {availability.staff_member_id for availability in availabilities}

        appointments = Appointment.objects.filter(
            start_time__date=self.date,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_ADVANCE,
            ],
        ).select_related('staff_member')

        busy_map = defaultdict(list)
        for appointment in appointments:
            if not appointment.staff_member_id:
                continue
            busy_start = appointment.start_time - self.buffer
            busy_end = appointment.end_time + self.buffer
            busy_map[appointment.staff_member_id].append((busy_start, busy_end))

        for staff_id in busy_map:
            busy_map[staff_id].sort()

        exclusion_map = defaultdict(list)
        tz = timezone.get_current_timezone()
        if staff_ids:
            exclusions = AvailabilityExclusion.objects.filter(
                staff_member_id__in=staff_ids,
            ).filter(
                Q(date=self.date) | Q(date__isnull=True, day_of_week=day_of_week)
            )
            for exclusion in exclusions:
                target_date = exclusion.date or self.date
                exclusion_start = timezone.make_aware(
                    datetime.combine(target_date, exclusion.start_time),
                    timezone=tz,
                )
                exclusion_end = timezone.make_aware(
                    datetime.combine(target_date, exclusion.end_time),
                    timezone=tz,
                )
                if exclusion_end <= exclusion_start:
                    continue
                exclusion_map[exclusion.staff_member_id].append((exclusion_start, exclusion_end))
            for staff_id in exclusion_map:
                exclusion_map[staff_id].sort()

        slots = []
        for availability in availabilities:
            staff = availability.staff_member
            block_start = timezone.make_aware(
                datetime.combine(self.date, availability.start_time),
                timezone=tz,
            )
            block_end = timezone.make_aware(
                datetime.combine(self.date, availability.end_time),
                timezone=tz,
            )

            if block_end <= block_start:
                continue

            busy_intervals = list(busy_map.get(staff.id, []))
            busy_intervals.extend(exclusion_map.get(staff.id, []))
            busy_intervals.sort()
            slot_start = block_start

            while slot_start + self.service_duration <= block_end:
                slot_end = slot_start + self.service_duration
                if slot_end + self.buffer > block_end:
                    break

                if not self._overlaps(busy_intervals, slot_start, slot_end):
                    slots.append({
                        "start_time": slot_start,
                        "staff_id": staff.id,
                        "staff_name": f"{staff.first_name} {staff.last_name}".strip() or staff.email,
                    })

                slot_start += self.slot_interval

        slots.sort(key=lambda slot: (slot["start_time"], slot["staff_name"]))
        return slots

    def _overlaps(self, intervals, start, end):
        for busy_start, busy_end in intervals:
            if start < busy_end and end > busy_start:
                return True
        return False


class AppointmentService:
    """
    Servicio para manejar la lógica de negocio de la creación de citas
    multisericio.
    """

    def __init__(self, user, services, staff_member, start_time):
        self.user = user
        self.services = list(services)
        self.staff_member = staff_member
        self.start_time = start_time
        self.buffer = timedelta(minutes=AvailabilityService.BUFFER_MINUTES)
        total_minutes = sum(service.duration for service in self.services)
        self.service_duration = timedelta(minutes=total_minutes)
        self.end_time = start_time + self.service_duration

    def _validate_appointment_rules(self):
        """Validaciones de reglas de negocio que no requieren bloqueo de BD."""
        if self.start_time < timezone.now():
            raise ValueError("No se puede reservar una cita en el pasado.")

        pending_payment = Payment.objects.filter(
            user=self.user,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        ).order_by("created_at").first()

        pending_appointment = Appointment.objects.filter(
            user=self.user,
            status=Appointment.AppointmentStatus.COMPLETED_PENDING_FINAL_PAYMENT,
        ).order_by("start_time").first()

        if pending_payment or pending_appointment:
            amount = pending_payment.amount if pending_payment else pending_appointment.price_at_purchase
            date = pending_payment.created_at.date() if pending_payment else pending_appointment.start_time.date()
            raise ValueError(
                f"Tienes un pago pendiente de ${amount} de la fecha {date}."
            )

        active_appointments = Appointment.objects.filter(
            user=self.user,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_ADVANCE,
            ]
        ).count()

        role_limits = {
            CustomUser.Role.CLIENT: 1,
            CustomUser.Role.VIP: 4,
        }
        limit = role_limits.get(self.user.role)
        if limit is not None and active_appointments >= limit:
            raise ValueError(
                f"Límite excedido. Tienes {active_appointments} citas activas y tu rol permite {limit}."
            )

    @transaction.atomic
    def create_appointment_with_lock(self):
        self._validate_appointment_rules()
        if self.staff_member:
            conflicting_appointments = Appointment.objects.select_for_update().filter(
                staff_member=self.staff_member,
                status__in=[
                    Appointment.AppointmentStatus.CONFIRMED,
                    Appointment.AppointmentStatus.PENDING_ADVANCE,
                ],
                start_time__lt=self.end_time + self.buffer,
                end_time__gt=self.start_time - self.buffer,
            ).exists()
            if conflicting_appointments:
                raise ValueError("El horario seleccionado ya no está disponible.")

        total_price = Decimal('0')
        appointment_items = []
        for service in self.services:
            item_price = self._get_price_for_service(service)
            appointment_items.append((service, item_price))
            total_price += item_price

        appointment = Appointment.objects.create(
            user=self.user,
            staff_member=self.staff_member,
            start_time=self.start_time,
            end_time=self.end_time,
            price_at_purchase=total_price,
            status=Appointment.AppointmentStatus.PENDING_ADVANCE
        )

        for service, price in appointment_items:
            AppointmentItem.objects.create(
                appointment=appointment,
                service=service,
                duration=service.duration,
                price_at_purchase=price,
            )

        payment_service = PaymentService(user=self.user)
        payment_service.create_advance_payment_for_appointment(appointment)

        return appointment

    @staticmethod
    @transaction.atomic
    def reschedule_appointment(appointment, new_start_time, acting_user):
        """
        Reagenda una cita existente aplicando las reglas de negocio.
        """
        if not isinstance(new_start_time, datetime):
            raise ValidationError("La fecha y hora nuevas no son válidas.")

        is_privileged = acting_user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        now = timezone.now()
        restrictions = []

        if appointment.start_time - now <= timedelta(hours=24):
            restrictions.append("window")
        if appointment.reschedule_count >= 2:
            restrictions.append("limit")

        if restrictions and not is_privileged:
            raise ValidationError(
                "Solo puedes reagendar hasta dos veces y con más de 24 horas de anticipación."
            )
        if restrictions and is_privileged:
            logger.info(
                "Staff %s bypassed reschedule restrictions (%s) for appointment %s",
                acting_user.id,
                ",".join(restrictions),
                appointment.id,
            )

        if not is_privileged and appointment.user != acting_user:
            raise ValidationError("No puedes modificar citas de otros usuarios.")

        if new_start_time <= now:
            raise ValidationError("La nueva fecha debe estar en el futuro.")

        duration = timedelta(minutes=appointment.total_duration_minutes)
        new_end_time = new_start_time + duration
        buffer = timedelta(minutes=AvailabilityService.BUFFER_MINUTES)

        if appointment.staff_member:
            conflict = (
                Appointment.objects.select_for_update()
                .filter(
                    staff_member=appointment.staff_member,
                    status__in=[
                        Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_ADVANCE,
                    ],
                )
                .exclude(id=appointment.id)
                .filter(
                    start_time__lt=new_end_time + buffer,
                    end_time__gt=new_start_time - buffer,
                )
                .exists()
            )
            if conflict:
                raise ValidationError("El nuevo horario ya no está disponible.")

        appointment.start_time = new_start_time
        appointment.end_time = new_end_time
        appointment.reschedule_count = appointment.reschedule_count + 1
        appointment.save(
            update_fields=['start_time', 'end_time', 'reschedule_count', 'updated_at']
        )
        return appointment

    @staticmethod
    def build_ical_event(appointment):
        """
        Construye un payload iCal simple para la cita.
        """
        dtstamp = timezone.now().astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dtstart = appointment.start_time.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dtend = appointment.end_time.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        summary = appointment.get_service_names() or "Cita ZenzSpa"
        description = f"Cita #{appointment.id}"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ZenzSpa//Appointments//ES",
            "BEGIN:VEVENT",
            f"UID:{appointment.id}@zenzspa",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{summary}",
            "LOCATION:ZenzSpa",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"

    def _get_price_for_service(self, service):
        if self.user.role == CustomUser.Role.VIP and service.vip_price is not None:
            return service.vip_price
        return service.price

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

        if package.grants_vip_months:
            VipMembershipService.extend_membership(payment.user, package.grants_vip_months)

        return user_package


class VipMembershipService:
    """
    Funciones auxiliares para manejar la extensión de membresías VIP.
    """

    @staticmethod
    @transaction.atomic
    def extend_membership(user, months):
        if not user:
            return None, None
        months = int(months or 0)
        if months <= 0:
            return None, None
        today = timezone.now().date()
        start_date = today
        if user.is_vip and user.vip_expires_at and user.vip_expires_at >= today:
            start_date = user.vip_expires_at + timedelta(days=1)
        end_date = start_date + timedelta(days=30 * months)
        user.role = CustomUser.Role.VIP
        update_fields = ['role', 'vip_expires_at', 'updated_at']
        user.vip_expires_at = end_date
        if not user.vip_active_since:
            user.vip_active_since = start_date
            update_fields.append('vip_active_since')
        user.save(update_fields=update_fields)
        return start_date, end_date
    
class VipSubscriptionService:
    """
    Servicio para manejar la lógica de negocio de las suscripciones VIP.
    """
    @staticmethod
    @transaction.atomic
    def fulfill_subscription(payment: Payment, months=1):
        user = payment.user
        start_date, end_date = VipMembershipService.extend_membership(user, months)
        if not start_date:
            return
        user.vip_auto_renew = True
        user.vip_failed_payments = 0
        user.save(update_fields=['vip_auto_renew', 'vip_expires_at', 'role', 'vip_active_since', 'vip_failed_payments', 'updated_at'])
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
    def __init__(self, request_data, headers=None):
        if isinstance(request_data, dict):
            self.request_body = request_data
        else:
            try:
                self.request_body = dict(request_data)
            except Exception:
                self.request_body = {}
        self.data = self.request_body.get("data", {})
        self.event_type = self.request_body.get("event")
        self.sent_signature = self.request_body.get("signature", {}).get("checksum")
        self.timestamp = self.request_body.get("timestamp")
        self.headers = headers or {}
        self.event_record = WebhookEvent.objects.create(
            payload=self.request_body,
            headers=dict(self.headers),
            event_type=self.event_type or "",
            status=WebhookEvent.Status.PROCESSED,
        )

    def _validate_signature(self):
        """
        Valida la firma del evento para asegurar que proviene de Wompi.
        """
        if not all([self.data, self.sent_signature, self.timestamp]):
            raise ValueError("Firma o datos del webhook incompletos.")
        
        # El cuerpo del evento (data) debe ser convertido a un string JSON compacto.
        event_body_str = json.dumps(self.data, separators=(',', ':'))
        
        # La cadena a firmar es: body + timestamp + secreto_de_eventos
        concatenation = f"{event_body_str}{self.timestamp}{settings.WOMPI_EVENT_SECRET}"
        
        calculated_signature = hashlib.sha256(concatenation.encode('utf-8')).hexdigest()
        
        if not hashlib.sha256(self.sent_signature.encode('utf-8')).hexdigest() == hashlib.sha256(calculated_signature.encode('utf-8')).hexdigest():
            raise ValueError("Firma del webhook inválida. La petición podría ser fraudulenta.")

    def _update_event_status(self, status, error_message=None):
        self.event_record.status = status
        self.event_record.error_message = error_message or ""
        self.event_record.save(update_fields=['status', 'error_message', 'updated_at'])

    @transaction.atomic
    def process_transaction_update(self):
        """
        Procesa un evento 'transaction.updated'.
        Es idempotente y seguro.
        """
        try:
            self._validate_signature()

            transaction_data = self.data.get("transaction", {})
            reference = transaction_data.get("reference")
            transaction_status = transaction_data.get("status")

            if not reference or not transaction_status:
                raise ValueError("Referencia o estado de la transacción ausentes en el webhook.")
            
            try:
                payment = Payment.objects.select_for_update().get(
                    transaction_id=reference,
                    status=Payment.PaymentStatus.PENDING,
                )
            except Payment.DoesNotExist:
                try:
                    order = Order.objects.select_for_update().get(wompi_transaction_id=reference)
                except Order.DoesNotExist:
                    self._update_event_status(WebhookEvent.Status.IGNORED, "Pago u orden no encontrados.")
                    return {"status": "already_processed_or_invalid"}

                amount_in_cents = transaction_data.get("amount_in_cents")
                expected_cents = int((order.total_amount or Decimal('0')) * Decimal('100'))

                if transaction_status == 'APPROVED':
                    if amount_in_cents is None or int(amount_in_cents) != expected_cents:
                        order.status = Order.OrderStatus.FRAUD_ALERT
                        order.fraud_reason = "Monto pagado no coincide con el total."
                        order.save(update_fields=['status', 'fraud_reason', 'updated_at'])
                        self._update_event_status(WebhookEvent.Status.FAILED, "Diferencia en montos detectada.")
                        return {"status": "fraud_alert"}
                    order.wompi_transaction_id = transaction_data.get("id", order.wompi_transaction_id)
                    order.save(update_fields=['wompi_transaction_id', 'updated_at'])
                    from marketplace.services import OrderService
                    OrderService.transition_to(order, Order.OrderStatus.PAID)
                else:
                    from marketplace.services import OrderService
                    OrderService.transition_to(order, Order.OrderStatus.CANCELLED)
                self._update_event_status(WebhookEvent.Status.PROCESSED)
                return {"status": "order_processed", "order_id": str(order.id)}

            PaymentService.apply_gateway_status(payment, transaction_status, transaction_data)
            self._update_event_status(WebhookEvent.Status.PROCESSED)
            return {"status": "processed_successfully", "payment_id": payment.id}
        except Exception as exc:
            self._update_event_status(WebhookEvent.Status.FAILED, str(exc))
            raise

class PaymentService:
    """
    Servicio para manejar la lógica de negocio de los pagos,
    incluyendo la aplicación de saldo a favor (ClientCredit).
    """
    def __init__(self, user):
        self.user = user

    @staticmethod
    def apply_gateway_status(payment, gateway_status, transaction_payload=None):
        normalized = (gateway_status or "").upper()
        if transaction_payload is not None:
            payment.raw_response = transaction_payload
        if normalized == 'APPROVED':
            if transaction_payload:
                payment.transaction_id = transaction_payload.get("id", payment.transaction_id)
            payment.status = Payment.PaymentStatus.APPROVED
            payment.save(update_fields=['status', 'transaction_id', 'raw_response', 'updated_at'])
            if payment.payment_type == Payment.PaymentType.PACKAGE:
                PackagePurchaseService.fulfill_purchase(payment)
            elif payment.payment_type == Payment.PaymentType.ADVANCE and payment.appointment:
                payment.appointment.status = Appointment.AppointmentStatus.CONFIRMED
                payment.appointment.save(update_fields=['status', 'updated_at'])
            elif payment.payment_type == Payment.PaymentType.VIP_SUBSCRIPTION:
                VipSubscriptionService.fulfill_subscription(payment)
        elif normalized in ('DECLINED', 'VOIDED'):
            payment.status = Payment.PaymentStatus.DECLINED
            payment.save(update_fields=['status', 'raw_response', 'updated_at'])
        elif normalized == 'PENDING':
            payment.status = Payment.PaymentStatus.PENDING
            payment.save(update_fields=['status', 'raw_response', 'updated_at'])
        else:
            payment.status = Payment.PaymentStatus.ERROR
            payment.save(update_fields=['status', 'raw_response', 'updated_at'])
        return payment.status

    @staticmethod
    def poll_pending_payment(payment, timeout_minutes=30):
        if payment.status != Payment.PaymentStatus.PENDING:
            return False
        if not payment.transaction_id:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        client = WompiClient()
        try:
            transaction = client.fetch_transaction(payment.transaction_id)
        except Exception:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        if not transaction:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        transaction_data = transaction.get('data') or transaction
        transaction_status = transaction_data.get('status')
        if not transaction_status:
            payment.status = Payment.PaymentStatus.TIMEOUT
            payment.save(update_fields=['status', 'updated_at'])
            return False
        PaymentService.apply_gateway_status(payment, transaction_status, transaction_data)
        return True

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

    @staticmethod
    @transaction.atomic
    def create_tip_payment(appointment: Appointment, user, amount):
        if appointment.status not in [
            Appointment.AppointmentStatus.COMPLETED,
            Appointment.AppointmentStatus.COMPLETED_PENDING_FINAL_PAYMENT,
        ]:
            raise ValidationError("Solo se pueden registrar propinas para citas completadas.")
        return Payment.objects.create(
            user=user,
            appointment=appointment,
            amount=amount,
            payment_type=Payment.PaymentType.TIP,
            status=Payment.PaymentStatus.APPROVED,
        )


class WaitlistService:
    OFFER_TTL_MINUTES = 30

    @classmethod
    def recycle_expired_offers(cls):
        now = timezone.now()
        expired = WaitlistEntry.objects.filter(
            status=WaitlistEntry.Status.OFFERED,
            offer_expires_at__lt=now,
        )
        for entry in expired:
            entry.reset_offer()

    @classmethod
    def offer_slot_for_appointment(cls, appointment):
        if appointment is None:
            return

        cls.recycle_expired_offers()

        service_ids = list(appointment.services.values_list('id', flat=True))
        queryset = WaitlistEntry.objects.filter(
            status=WaitlistEntry.Status.WAITING,
            desired_date=appointment.start_time.date(),
        )
        if service_ids:
            queryset = queryset.filter(
                Q(services__isnull=True) | Q(services__in=service_ids)
            )

        entry = queryset.order_by('created_at').distinct().first()
        if not entry:
            return

        entry.mark_offered(appointment, cls.OFFER_TTL_MINUTES)
        try:
            from .tasks import notify_waitlist_availability
            notify_waitlist_availability.delay(str(entry.id))
        except Exception:
            logger.exception("No se pudo programar la notificación de lista de espera.")


class FinancialAdjustmentService:
    CREDIT_TTL_DAYS = 365

    @classmethod
    @transaction.atomic
    def create_adjustment(cls, *, user, amount, adjustment_type, reason, created_by, related_payment=None):
        if amount <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")
        adjustment = FinancialAdjustment.objects.create(
            user=user,
            amount=amount,
            adjustment_type=adjustment_type,
            reason=reason,
            related_payment=related_payment,
            created_by=created_by,
        )
        if adjustment_type == FinancialAdjustment.AdjustmentType.CREDIT:
            expires = timezone.now().date() + timedelta(days=cls.CREDIT_TTL_DAYS)
            ClientCredit.objects.create(
                user=user,
                originating_payment=related_payment,
                initial_amount=amount,
                remaining_amount=amount,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires,
            )
        return adjustment


class CreditService:
    """
    Helper para generar ClientCredit según las políticas vigentes.
    """

    @staticmethod
    @transaction.atomic
    def create_credit_from_appointment(*, appointment, percentage, created_by, reason):
        percentage = Decimal(str(percentage))
        if percentage <= 0:
            return Decimal('0')
        payments = appointment.payments.select_for_update().filter(
            payment_type=Payment.PaymentType.ADVANCE,
            status__in=[
                Payment.PaymentStatus.APPROVED,
                Payment.PaymentStatus.PAID_WITH_CREDIT,
            ],
        )
        if not payments.exists():
            return Decimal('0')

        settings = GlobalSettings.load()
        expires_at = timezone.now().date() + timedelta(days=settings.credit_expiration_days)
        total_created = Decimal('0')
        for payment in payments:
            if hasattr(payment, "generated_credit"):
                continue
            credit_amount = (payment.amount or Decimal('0')) * percentage
            if credit_amount <= 0:
                continue
            ClientCredit.objects.create(
                user=appointment.user,
                originating_payment=payment,
                initial_amount=credit_amount,
                remaining_amount=credit_amount,
                status=ClientCredit.CreditStatus.AVAILABLE,
                expires_at=expires_at,
            )
            total_created += credit_amount

        if total_created > 0:
            AuditLog.objects.create(
                admin_user=created_by,
                target_user=appointment.user,
                target_appointment=appointment,
                action=AuditLog.Action.APPOINTMENT_CANCELLED_BY_ADMIN,
                details=reason or f"Crédito generado por cita {appointment.id}",
            )
        return total_created


class WompiClient:
    def __init__(self):
        self.base_url = getattr(settings, 'WOMPI_BASE_URL', '')
        self.private_key = getattr(settings, 'WOMPI_PRIVATE_KEY', '')

    def fetch_transaction(self, reference):
        if not self.base_url or not reference:
            return None
        url = f"{self.base_url.rstrip('/')}/transactions/{reference}"
        headers = {}
        if self.private_key:
            headers['Authorization'] = f"Bearer {self.private_key}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code >= 400:
            response.raise_for_status()
        return response.json()
