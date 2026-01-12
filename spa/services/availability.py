import logging
from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from core.infra.metrics import get_counter, get_histogram
from core.models import GlobalSettings
from ..models import (
    Appointment,
    AvailabilityExclusion,
    Service,
    StaffAvailability,
)

logger = logging.getLogger(__name__)

availability_duration = get_histogram(
    "availability_calculation_duration_seconds",
    "Duración del cálculo de disponibilidad",
    ["staff_filter"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5],
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
        self.service_duration = timedelta(minutes=sum(service.duration for service in self.services))
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
        from decimal import Decimal

        total = Decimal("0")
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
            day_of_week=day_of_week,
            staff_member__is_active=True,
        )

        if staff_member_id:
            availabilities = availabilities.filter(staff_member_id=staff_member_id)
        availabilities = list(availabilities.select_related("staff_member"))

        staff_ids = {availability.staff_member_id for availability in availabilities}

        appointments_qs = Appointment.objects.filter(
            start_time__date=self.date,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
                Appointment.AppointmentStatus.RESCHEDULED,
                Appointment.AppointmentStatus.FULLY_PAID,
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
            busy_map[appointment.staff_member_id].append((busy_start, busy_end))

        for staff_id in busy_map:
            busy_map[staff_id].sort()

        exclusion_map = defaultdict(list)
        tz = timezone.get_current_timezone()
        if staff_ids:
            exclusions = AvailabilityExclusion.objects.filter(
                staff_member_id__in=staff_ids,
                staff_member__is_active=True,
            ).filter(Q(date=self.date) | Q(date__isnull=True, day_of_week=day_of_week))
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

                if slot_start < now + minimum_advance:
                    slot_start += self.slot_interval
                    continue

                if slot_end + self.buffer > block_end:
                    break

                if not self._overlaps(busy_intervals, slot_start, slot_end):
                    slots.append(
                        {
                            "start_time": slot_start,
                            "staff_id": staff.id,
                            "staff_name": f"{staff.first_name} {staff.last_name}".strip() or staff.email,
                        }
                    )

                slot_start += self.slot_interval

        slots.sort(key=lambda slot: (slot["start_time"], slot["staff_id"]))

        staff_mapping = {}
        staff_index = 1
        for slot in slots:
            if slot["staff_id"] not in staff_mapping:
                staff_mapping[slot["staff_id"]] = f"Terapeuta {staff_index}"
                staff_index += 1

            slot["staff_label"] = staff_mapping[slot["staff_id"]]
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
