import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from core.utils.exceptions import BusinessLogicError
from core.infra.metrics import get_counter
from core.models import GlobalSettings
from core.utils import emit_metric
from finances.models import Payment
from users.models import CustomUser
from ..models import Appointment, AppointmentItem, AvailabilityExclusion, StaffAvailability
from .availability import AvailabilityService

logger = logging.getLogger(__name__)

booking_conflicts = get_counter(
    "appointment_concurrency_conflicts_total",
    "Conflictos de doble booking evitados",
    ["staff_id"],
)


class AppointmentServiceBase:
    """
    Base con la lógica de creación de citas y validaciones de negocio.
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
        self.is_low_supervision_bundle = all(service.category.is_low_supervision for service in self.services)
        self.local_timezone = timezone.get_current_timezone()

    def _validate_appointment_rules(self):
        emit_metric("booking.validate_start", tags={"staff_id": getattr(self.staff_member, "id", None)})
        if self.start_time < timezone.now():
            raise ValueError("No se puede reservar una cita en el pasado.")

        pending_payment = Payment.objects.filter(
            user=self.user,
            status=Payment.PaymentStatus.PENDING,
            payment_type=Payment.PaymentType.FINAL,
        ).order_by("created_at").first()

        pending_appointment = None
        for appt in Appointment.objects.filter(
            user=self.user,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.FULLY_PAID,
                Appointment.AppointmentStatus.COMPLETED,
            ],
        ).order_by("start_time"):
            outstanding = appt.outstanding_balance
            if outstanding > Decimal("0"):
                pending_appointment = appt
                break

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
                Appointment.AppointmentStatus.FULLY_PAID,
            ],
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
        ).filter(Q(date=local_start.date()) | Q(date__isnull=True, day_of_week=day_of_week)).filter(
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

        acquired = True
        try:
            if lock_key:
                from core.utils.caching import acquire_lock

                acquired = acquire_lock(lock_key, timeout=5)
            if not acquired:
                emit_metric("booking.lock_unavailable", tags={"staff_id": getattr(self.staff_member, "id", None)})
                raise BusinessLogicError(
                    detail="Sistema ocupado, intenta de nuevo en unos segundos.",
                    internal_code="APP-LOCK",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            if self.staff_member:
                self.staff_member = CustomUser.objects.select_for_update().get(pk=self.staff_member.pk)
                self._ensure_staff_is_available()
                conflicting_appointments = (
                    Appointment.objects.select_for_update()
                    .filter(
                        staff_member=self.staff_member,
                        status__in=[
                            Appointment.AppointmentStatus.CONFIRMED,
                            Appointment.AppointmentStatus.PENDING_PAYMENT,
                            Appointment.AppointmentStatus.RESCHEDULED,
                            Appointment.AppointmentStatus.FULLY_PAID,
                        ],
                        start_time__lt=self.end_time + self.buffer,
                        end_time__gt=self.start_time - self.buffer,
                    )
                    .exists()
                )
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

        total_price = Decimal("0")
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
            status=Appointment.AppointmentStatus.PENDING_PAYMENT,
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
            Appointment.AppointmentStatus.FULLY_PAID,
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

    def _get_price_for_service(self, service):
        if self.user.role == CustomUser.Role.VIP and service.vip_price is not None:
            return service.vip_price
        return service.price
