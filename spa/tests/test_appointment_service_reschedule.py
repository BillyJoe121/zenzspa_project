import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from model_bakery import baker

from spa.services import AppointmentService
from spa.models import Appointment, ServiceCategory, Service, StaffAvailability
from core.exceptions import BusinessLogicError


@pytest.mark.django_db
def test_reschedule_updates_fields(mocker):
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=30)
    staff = baker.make("users.CustomUser", role="STAFF")
    user = baker.make("users.CustomUser", role="CLIENT")
    now = timezone.now()
    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=now.isoweekday(),
        start_time=now.replace(hour=8, minute=0, second=0, microsecond=0).time(),
        end_time=now.replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )

    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    appt = baker.make(
        Appointment,
        user=user,
        staff_member=staff,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    appt.services.add(service)

    new_start = start + timedelta(hours=1)
    updated = AppointmentService.reschedule_appointment(appt, new_start, acting_user=user)
    assert updated.start_time == new_start
    assert updated.status == Appointment.AppointmentStatus.RESCHEDULED
    assert updated.reschedule_count == 1


@pytest.mark.django_db
def test_reschedule_conflict_raises(mocker):
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=30)
    staff = baker.make("users.CustomUser", role="STAFF")
    user = baker.make("users.CustomUser", role="CLIENT")
    now = timezone.now()
    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=now.isoweekday(),
        start_time=now.replace(hour=8, minute=0, second=0, microsecond=0).time(),
        end_time=now.replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )

    start = now.replace(hour=10, minute=0, second=0, microsecond=0)
    appt = baker.make(
        Appointment,
        user=user,
        staff_member=staff,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    appt.services.add(service)

    # Crear otra cita conflictiva
    conflict = baker.make(
        Appointment,
        user=user,
        staff_member=staff,
        start_time=start + timedelta(hours=1),
        end_time=start + timedelta(hours=1, minutes=30),
        status=Appointment.AppointmentStatus.CONFIRMED,
    )
    conflict.services.add(service)

    with pytest.raises(ValidationError):
        AppointmentService.reschedule_appointment(
            appt,
            conflict.start_time,
            acting_user=user,
        )
