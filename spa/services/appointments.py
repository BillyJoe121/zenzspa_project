import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status

from core.exceptions import BusinessLogicError
from core.utils import emit_metric
from core.metrics import get_histogram, get_counter
from core.models import AuditLog, GlobalSettings
from users.models import CustomUser
from ..models import (
    Appointment,
    AppointmentItem,
    AvailabilityExclusion,
    Service,
    StaffAvailability,
)
from finances.models import Payment
from finances.payments import PaymentService

logger = logging.getLogger(__name__)

availability_duration = get_histogram(
    "availability_calculation_duration_seconds",
    "Duración del cálculo de disponibilidad",
    ["staff_filter"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)
booking_conflicts = get_counter(
    "appointment_concurrency_conflicts_total",
    "Conflictos de doble booking evitados",
    ["staff_id"],
)

class AvailabilityService:
    """
    Calcula slots disponibles considerando múltiples servicios y buffer.
    """

    DEFAULT_BUFFER_MINUTES = 15
    SLOT_INTERVAL_MINUTES = 15

    def __init__(self, date, services):
        if not services:
            raise ValueError("Debes seleccionar al menos un servicio.")
        self.date = date
        self.services = list(services)
        self.buffer = self._buffer_delta()
        self.slot_interval = timedelta(minutes=self.SLOT_INTERVAL_MINUTES)
        self.service_duration = timedelta(
            minutes=sum(service.duration for service in self.services)
        )
        if self.service_duration <= timedelta(0):
            raise ValueError(
                "Los servicios seleccionados no tienen duración válida.")

    @classmethod
    def for_service_ids(cls, date, service_ids):
        services = list(Service.objects.filter(
            id__in=service_ids, is_active=True))
        if len(services) != len(set(service_ids)):
            raise ValueError(
                "Uno o más servicios seleccionados no existen o están inactivos.")
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
        start = timezone.now()
        day_of_week = self.date.isoweekday()
        availabilities = StaffAvailability.objects.filter(
            day_of_week=day_of_week)
        if staff_member_id:
            availabilities = availabilities.filter(
                staff_member_id=staff_member_id)
        availabilities = list(availabilities.select_related('staff_member'))
        
        # OPTIMIZATION: Filter staff who can actually perform the requested services
        # This assumes we have a way to know which staff can do which service.
        # If not implemented yet, we skip this specific filter or add a TODO.
        # For now, we will filter out staff that have NO availability at all (already done by query)
        
        staff_ids = {
            availability.staff_member_id for availability in availabilities}

        appointments_qs = Appointment.objects.filter(
            start_time__date=self.date,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
                Appointment.AppointmentStatus.RESCHEDULED,
            ],
            staff_member_id__isnull=False,
        ).only("start_time", "end_time", "staff_member_id")

        if staff_ids:
            appointments_qs = appointments_qs.filter(staff_member_id__in=staff_ids)

        appointments = appointments_qs.iterator()

        busy_map = defaultdict(list)
        for appointment in appointments:
            if not appointment.staff_member_id:
                continue
            busy_start = appointment.start_time - self.buffer
            busy_end = appointment.end_time + self.buffer
            busy_map[appointment.staff_member_id].append(
                (busy_start, busy_end))

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
                exclusion_map[exclusion.staff_member_id].append(
                    (exclusion_start, exclusion_end))
            for staff_id in exclusion_map:
                exclusion_map[staff_id].sort()

        slots = []
        now = timezone.now()
        minimum_advance = timedelta(minutes=30)

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

                # Validar anticipación mínima de 30 minutos
                if slot_start < now + minimum_advance:
                    slot_start += self.slot_interval
                    continue

                if slot_end + self.buffer > block_end:
                    break

                if not self._overlaps(busy_intervals, slot_start, slot_end):
                    slots.append({
                        "start_time": slot_start,
                        "staff_id": staff.id,
                        "staff_name": f"{staff.first_name} {staff.last_name}".strip() or staff.email,
                    })

                slot_start += self.slot_interval

        slots.sort(key=lambda slot: (slot["start_time"], slot["staff_id"]))

        # Anonimizar staff creando etiquetas genéricas
        staff_mapping = {}
        staff_index = 1
        for slot in slots:
            if slot["staff_id"] not in staff_mapping:
                staff_mapping[slot["staff_id"]] = f"Terapeuta {staff_index}"
                staff_index += 1

            slot["staff_label"] = staff_mapping[slot["staff_id"]]
            # Remover staff_name para no exponer nombres reales
            del slot["staff_name"]

        duration = (timezone.now() - start).total_seconds()
        availability_duration.labels(bool(staff_member_id)).observe(duration)
        return slots

    def _overlaps(self, intervals, start, end):
        for busy_start, busy_end in intervals:
            if start < busy_end and end > busy_start:
                return True
        return False

    @classmethod
    def _buffer_minutes(cls):
        minutes = None
        try:
            minutes = GlobalSettings.load().appointment_buffer_time
        except Exception:
            minutes = None
        if not minutes or minutes <= 0:
            return cls.DEFAULT_BUFFER_MINUTES
        return minutes

    @classmethod
    def _buffer_delta(cls):
        return timedelta(minutes=cls._buffer_minutes())


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
        self.buffer = AvailabilityService._buffer_delta()
        total_minutes = sum(service.duration for service in self.services)
        self.service_duration = timedelta(minutes=total_minutes)
        self.end_time = start_time + self.service_duration
        self.is_low_supervision_bundle = all(
            service.category.is_low_supervision for service in self.services
        )
        self.local_timezone = timezone.get_current_timezone()

    def _validate_appointment_rules(self):
        """Validaciones de reglas de negocio que no requieren bloqueo de BD."""
        emit_metric(
            "booking.validate_start",
            tags={"staff_id": getattr(self.staff_member, "id", None)},
        )
        if self.start_time < timezone.now():
            raise ValueError("No se puede reservar una cita en el pasado.")

        pending_payment = Payment.objects.filter(
            user=self.user,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        ).order_by("created_at").first()

        pending_appointment = Appointment.objects.filter(
            user=self.user,
            status=Appointment.AppointmentStatus.PAID,
        ).order_by("start_time").first()

        if pending_payment or pending_appointment:
            raise BusinessLogicError(
                detail="Usuario bloqueado por deuda pendiente.",
                internal_code="APP-004",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        active_appointments = Appointment.objects.filter(
            user=self.user,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
                Appointment.AppointmentStatus.RESCHEDULED,
            ]
        ).count()

        role_limits = {
            CustomUser.Role.CLIENT: 1,
            CustomUser.Role.VIP: 4,
        }
        limit = role_limits.get(self.user.role)
        if limit is not None and active_appointments >= limit:
            raise BusinessLogicError(
                detail="Límite de citas activas excedido.",
                internal_code="APP-003",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    def _ensure_staff_is_available(self):
        if not self.staff_member:
            return
        local_start = self.start_time.astimezone(self.local_timezone)
        local_end = self.end_time.astimezone(self.local_timezone)
        day_of_week = local_start.isoweekday()
        availability_exists = StaffAvailability.objects.filter(
            staff_member=self.staff_member,
            day_of_week=day_of_week,
            start_time__lte=local_start.time(),
            end_time__gte=local_end.time(),
        ).exists()
        if not availability_exists:
            raise BusinessLogicError(
                detail="El staff no trabaja en este horario.",
                internal_code="APP-002",
                status_code=status.HTTP_409_CONFLICT,
            )

        exclusion_exists = AvailabilityExclusion.objects.filter(
            staff_member=self.staff_member,
        ).filter(
            Q(date=local_start.date()) | Q(
                date__isnull=True, day_of_week=day_of_week)
        ).filter(
            start_time__lt=local_end.time(),
            end_time__gt=local_start.time(),
        ).exists()
        if exclusion_exists:
            raise BusinessLogicError(
                detail="El staff no trabaja en este horario.",
                internal_code="APP-002",
                status_code=status.HTTP_409_CONFLICT,
            )

    @transaction.atomic
    def create_appointment_with_lock(self):
        self._validate_appointment_rules()
        lock_key = None
        if self.staff_member:
            lock_key = f"appt:staff:{self.staff_member.id}:{self.start_time.isoformat()}"
        else:
            lock_key = f"appt:low_supervision:{self.start_time.isoformat()}"
        # Fallback a SELECT FOR UPDATE en staff, pero intentamos lock distribuido para nodos múltiples.
        acquired = True
        try:
            if lock_key:
                from core.caching import acquire_lock
                acquired = acquire_lock(lock_key, timeout=5)
            if not acquired:
                emit_metric("booking.lock_unavailable", tags={"staff_id": getattr(self.staff_member, 'id', None)})
                raise BusinessLogicError(
                    detail="Sistema ocupado, intenta de nuevo en unos segundos.",
                    internal_code="APP-LOCK",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            if self.staff_member:
                # Lock en staff para evitar carreras de disponibilidad
                self.staff_member = CustomUser.objects.select_for_update().get(pk=self.staff_member.pk)
                self._ensure_staff_is_available()
                conflicting_appointments = Appointment.objects.select_for_update().filter(
                    staff_member=self.staff_member,
                    status__in=[
                        Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT,
                        Appointment.AppointmentStatus.RESCHEDULED,
                    ],
                    start_time__lt=self.end_time + self.buffer,
                    end_time__gt=self.start_time - self.buffer,
                ).exists()
                if conflicting_appointments:
                    booking_conflicts.labels(str(self.staff_member.id)).inc()
                    emit_metric(
                        "booking.conflict",
                        tags={
                            "staff_id": self.staff_member.id,
                            "start": self.start_time.isoformat(),
                        },
                    )
                    logger.warning(
                        "Conflicto de agenda detectado staff=%s start=%s end=%s",
                        self.staff_member.id,
                        self.start_time.isoformat(),
                        self.end_time.isoformat(),
                    )
                    raise BusinessLogicError(
                        detail="Horario no disponible por solapamiento.",
                        internal_code="APP-001",
                        status_code=status.HTTP_409_CONFLICT,
                    )
            elif self.is_low_supervision_bundle:
                self._enforce_low_supervision_capacity()
        finally:
            if lock_key:
                try:
                    from django.core.cache import cache
                    cache.delete(lock_key)
                except Exception:
                    pass

        total_price = Decimal('0')
        appointment_items = []
        seen_services = set()
        for service in self.services:
            if service.id in seen_services:
                raise BusinessLogicError(
                    detail=f"El servicio '{service.name}' está duplicado en la solicitud.",
                    internal_code="APP-005",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            seen_services.add(service.id)
            item_price = self._get_price_for_service(service)
            appointment_items.append((service, item_price))
            total_price += item_price

        appointment = Appointment.objects.create(
            user=self.user,
            staff_member=self.staff_member,
            start_time=self.start_time,
            end_time=self.end_time,
            price_at_purchase=total_price,
            status=Appointment.AppointmentStatus.PENDING_PAYMENT
        )
        emit_metric(
            "booking.success",
            tags={
                "staff_id": getattr(self.staff_member, "id", None),
                "is_low_supervision": self.is_low_supervision_bundle,
            },
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

    def _enforce_low_supervision_capacity(self):
        settings_obj = GlobalSettings.load()
        capacity = settings_obj.low_supervision_capacity or 0
        if capacity <= 0:
            return
        active_statuses = [
            Appointment.AppointmentStatus.CONFIRMED,
            Appointment.AppointmentStatus.PENDING_PAYMENT,
            Appointment.AppointmentStatus.RESCHEDULED,
        ]
        concurrent_count = (
            Appointment.objects.select_for_update()
            .filter(
                staff_member__isnull=True,
                status__in=active_statuses,
                start_time=self.start_time,
            )
            .count()
        )
        if concurrent_count >= capacity:
            raise BusinessLogicError(
                detail="Capacidad máxima alcanzada para este horario. Selecciona otro horario o espera un espacio disponible.",
                internal_code="SRV-003",
                status_code=status.HTTP_409_CONFLICT,
            )

    @staticmethod
    @transaction.atomic
    def reschedule_appointment(appointment, new_start_time, acting_user):
        """
        Reagenda una cita existente aplicando las reglas de negocio.
        """
        if not isinstance(new_start_time, datetime):
            raise ValidationError("La fecha y hora nuevas no son válidas.")

        is_privileged = acting_user.role in [
            CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
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
            AuditLog.objects.create(
                admin_user=acting_user,
                target_user=appointment.user,
                target_appointment=appointment,
                action=AuditLog.Action.APPOINTMENT_RESCHEDULE_FORCE,
                details="Reagendamiento forzado por Staff fuera de ventana de política.",
            )

        if not is_privileged and appointment.user != acting_user:
            raise ValidationError(
                "No puedes modificar citas de otros usuarios.")

        if new_start_time <= now:
            raise ValidationError("La nueva fecha debe estar en el futuro.")

        duration = timedelta(minutes=appointment.total_duration_minutes)
        new_end_time = new_start_time + duration
        buffer = AvailabilityService._buffer_delta()

        if appointment.staff_member:
            conflict = (
                Appointment.objects.select_for_update()
                .filter(
                    staff_member=appointment.staff_member,
                    status__in=[
                        Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT,
                        Appointment.AppointmentStatus.RESCHEDULED,
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
                raise ValidationError(
                    "El nuevo horario ya no está disponible.")

        appointment.start_time = new_start_time
        appointment.end_time = new_end_time
        appointment.reschedule_count = appointment.reschedule_count + 1
        appointment.status = Appointment.AppointmentStatus.RESCHEDULED
        appointment.save(
            update_fields=['start_time', 'end_time',
                           'reschedule_count', 'status', 'updated_at']
        )
        return appointment

    @staticmethod
    @transaction.atomic
    def complete_appointment(appointment, acting_user):
        if acting_user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            raise ValidationError(
                "No tienes permisos para completar esta cita.")
        outstanding = PaymentService.calculate_outstanding_amount(appointment)
        if outstanding > 0:
            raise ValidationError(
                "No puedes completar la cita: existe un saldo final pendiente.")
        appointment.status = Appointment.AppointmentStatus.COMPLETED
        appointment.outcome = Appointment.AppointmentOutcome.NONE
        appointment.save(update_fields=['status', 'outcome', 'updated_at'])
        PaymentService.reset_user_cancellation_history(appointment)
        AuditLog.objects.create(
            admin_user=acting_user,
            target_user=appointment.user,
            target_appointment=appointment,
            action=AuditLog.Action.APPOINTMENT_COMPLETED,
            details=f"Cita {appointment.id} marcada como COMPLETED por {getattr(acting_user, 'phone_number', 'staff')}.",
        )
        return appointment

    @staticmethod
    def build_ical_event(appointment):
        """
        Construye un payload iCal simple para la cita.
        """
        dtstamp = timezone.now().astimezone(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dtstart = appointment.start_time.astimezone(
            dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dtend = appointment.end_time.astimezone(
            dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        summary = appointment.get_service_names() or "Cita StudioZens"
        description = f"Cita #{appointment.id}"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//StudioZens//Appointments//ES",
            "BEGIN:VEVENT",
            f"UID:{appointment.id}@studiozens",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{summary}",
            "LOCATION:StudioZens",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"

    def _get_price_for_service(self, service):
        if self.user.role == CustomUser.Role.VIP and service.vip_price is not None:
            return service.vip_price
        return service.price
