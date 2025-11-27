import pytest
from datetime import timedelta
from django.utils import timezone
from model_bakery import baker

from spa.services import AppointmentService
from spa.models import Appointment, Service, ServiceCategory, StaffAvailability, Payment
from core.exceptions import BusinessLogicError


@pytest.mark.django_db
def test_create_appointment_blocks_conflict(mocker):
    # Datos base
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make("users.CustomUser", role="STAFF")
    user = baker.make("users.CustomUser", role="CLIENT")
    # Remover disponibilidad por defecto si existe
    StaffAvailability.objects.filter(staff_member=staff).delete()
    # Evitar solapamiento inicial y permitir agenda
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=timezone.now().isoweekday(),
        start_time=timezone.now().replace(hour=8, minute=0, second=0, microsecond=0).time(),
        end_time=timezone.now().replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )
    # Disponibilidad del staff
    now = timezone.now()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=now.isoweekday(),
        start_time=now.replace(hour=8, minute=0, second=0, microsecond=0).time(),
        end_time=now.replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )
    start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)

    # Evitar efectos colaterales de pago
    mocker.patch("spa.services.appointments.PaymentService.create_advance_payment_for_appointment", return_value=None)

    # Primer booking debe pasar
    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=start_time)
    appt = svc.create_appointment_with_lock()
    assert isinstance(appt, Appointment)
    assert appt.staff_member == staff
    assert appt.status == Appointment.AppointmentStatus.PENDING_PAYMENT

    # Segundo booking mismo slot debe fallar
    svc_conflict = AppointmentService(user=user, services=[service], staff_member=staff, start_time=start_time)
    with pytest.raises(BusinessLogicError):
        svc_conflict.create_appointment_with_lock()
