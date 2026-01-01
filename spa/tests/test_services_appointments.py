import pytest
from datetime import timedelta, date
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from model_bakery import baker

from spa.services import AppointmentService
from spa.services.appointments import AvailabilityService
from spa.models import Appointment, Service, ServiceCategory, StaffAvailability, AvailabilityExclusion
from core.exceptions import BusinessLogicError
from core.models import GlobalSettings, AuditLog
from finances.models import Payment
from users.models import CustomUser
from django.core.cache import cache


@pytest.mark.django_db
def test_create_appointment_blocks_conflict(mocker):
    # Datos base
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make("users.CustomUser", role="STAFF")
    user1 = baker.make("users.CustomUser", role="CLIENT")
    user2 = baker.make("users.CustomUser", role="CLIENT")  # Segundo usuario para evitar límite de citas
    # Remover disponibilidad por defecto si existe
    StaffAvailability.objects.filter(staff_member=staff).delete()
    # Disponibilidad del staff - usar fecha futura en timezone local
    local_tz = timezone.get_current_timezone()
    now = timezone.now().astimezone(local_tz) + timedelta(days=2)
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=now.isoweekday(),
        start_time=now.replace(hour=8, minute=0, second=0, microsecond=0).time(),
        end_time=now.replace(hour=20, minute=0, second=0, microsecond=0).time(),
    )
    start_time = now.replace(hour=10, minute=0, second=0, microsecond=0)

    # Evitar efectos colaterales de pago y lock distribuido
    mocker.patch("spa.services.appointments.PaymentService.create_advance_payment_for_appointment", return_value=None)
    mocker.patch("core.caching.acquire_lock", return_value=True)  # Simular que siempre se adquiere el lock
    metric_mock = mocker.patch("spa.services.appointments.emit_metric")

    # Primer booking debe pasar
    svc = AppointmentService(user=user1, services=[service], staff_member=staff, start_time=start_time)
    appt = svc.create_appointment_with_lock()
    assert isinstance(appt, Appointment)
    assert appt.staff_member == staff
    assert appt.status == Appointment.AppointmentStatus.PENDING_PAYMENT

    # Segundo booking mismo slot con OTRO USUARIO debe fallar con conflicto de horario
    svc_conflict = AppointmentService(user=user2, services=[service], staff_member=staff, start_time=start_time)
    with pytest.raises(BusinessLogicError) as exc_info:
        svc_conflict.create_appointment_with_lock()

    # Verificar que es el error de conflicto correcto (APP-001 = solapamiento de horario)
    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-001", f"Expected APP-001 (conflict), got {error_code}"

    # Métricas fueron emitidas (success + conflict)
    metric_events = [call.args[0] for call in metric_mock.call_args_list]
    assert "booking.success" in metric_events
    assert "booking.conflict" in metric_events

    # liberar locks
    cache.clear()


# ============================================================
# Tests for AvailabilityService
# ============================================================

@pytest.mark.django_db
def test_availability_service_no_services_raises():
    """Test that AvailabilityService raises ValueError when no services provided."""
    target_date = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="Debes seleccionar al menos un servicio"):
        AvailabilityService(target_date, [])


@pytest.mark.django_db
def test_availability_service_zero_duration_raises():
    """Test that AvailabilityService raises ValueError when services have zero duration."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=0)
    target_date = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="no tienen duración válida"):
        AvailabilityService(target_date, [service])


@pytest.mark.django_db
def test_availability_service_for_service_ids_inactive_service():
    """Test that for_service_ids raises ValueError when service is inactive."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    active_service = baker.make(Service, category=category, duration=30, is_active=True)
    inactive_service = baker.make(Service, category=category, duration=30, is_active=False)
    target_date = date.today() + timedelta(days=1)

    with pytest.raises(ValueError, match="no existen o están inactivos"):
        AvailabilityService.for_service_ids(target_date, [active_service.id, inactive_service.id])


@pytest.mark.django_db
def test_availability_service_total_price_for_vip_user():
    """Test that total_price_for_user returns VIP price for VIP users."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=30, price=Decimal('100.00'), vip_price=Decimal('80.00'))
    # VIP role alone should trigger VIP pricing (is_vip is a computed property)
    vip_user = baker.make(CustomUser, role=CustomUser.Role.VIP)
    target_date = date.today() + timedelta(days=1)

    availability_svc = AvailabilityService(target_date, [service])
    total = availability_svc.total_price_for_user(vip_user)

    assert total == Decimal('80.00')


@pytest.mark.django_db
def test_availability_service_total_price_for_regular_user():
    """Test that total_price_for_user returns regular price for regular users."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=30, price=Decimal('100.00'), vip_price=Decimal('80.00'))
    regular_user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)
    target_date = date.today() + timedelta(days=1)

    availability_svc = AvailabilityService(target_date, [service])
    total = availability_svc.total_price_for_user(regular_user)

    assert total == Decimal('100.00')


@pytest.mark.django_db
def test_availability_service_get_available_slots_with_staff_filter():
    """Test get_available_slots with specific staff member filter."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60, is_active=True)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF, first_name="John", last_name="Doe")

    local_tz = timezone.get_current_timezone()
    target_date = (timezone.now() + timedelta(days=1)).date()
    day_of_week = target_date.isoweekday()

    # Remove auto-created availability
    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    slots = AvailabilityService.get_available_slots(target_date, [service.id], staff_member_id=staff.id)

    assert len(slots) > 0
    assert all(slot['staff_id'] == staff.id for slot in slots)


@pytest.mark.django_db
def test_availability_service_with_exclusions():
    """Test that availability exclusions properly block slots."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60, is_active=True)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)

    local_tz = timezone.get_current_timezone()
    target_date = (timezone.now() + timedelta(days=1)).date()
    day_of_week = target_date.isoweekday()

    # Remove auto-created availability and add our specific availability
    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    # Add exclusion for specific date blocking 12:00-13:00
    baker.make(
        AvailabilityExclusion,
        staff_member=staff,
        date=target_date,
        start_time=timezone.datetime.strptime("12:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("13:00", "%H:%M").time(),
    )

    slots = AvailabilityService.get_available_slots(target_date, [service.id], staff_member_id=staff.id)

    # Verify that noon slot is not available
    noon_slots = [s for s in slots if s['start_time'].hour == 12 and s['start_time'].minute == 0]
    assert len(noon_slots) == 0


@pytest.mark.django_db
def test_availability_service_with_recurring_exclusion():
    """Test that recurring exclusions (day_of_week based) block slots."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60, is_active=True)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)

    local_tz = timezone.get_current_timezone()
    target_date = (timezone.now() + timedelta(days=1)).date()
    day_of_week = target_date.isoweekday()

    # Remove auto-created availability and add our specific availability
    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    # Add recurring exclusion (no specific date, just day_of_week)
    baker.make(
        AvailabilityExclusion,
        staff_member=staff,
        date=None,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("14:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("15:00", "%H:%M").time(),
    )

    slots = AvailabilityService.get_available_slots(target_date, [service.id], staff_member_id=staff.id)

    # Verify that 14:00 slot is not available
    two_pm_slots = [s for s in slots if s['start_time'].hour == 14 and s['start_time'].minute == 0]
    assert len(two_pm_slots) == 0


# ============================================================
# Tests for AppointmentService validations
# ============================================================

@pytest.mark.django_db
def test_appointment_service_past_time_raises(mocker):
    """Test that booking in the past raises ValueError."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    past_time = timezone.now() - timedelta(hours=1)

    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=past_time)

    with pytest.raises(ValueError, match="No se puede reservar una cita en el pasado"):
        svc._validate_appointment_rules()


@pytest.mark.django_db
def test_appointment_service_user_with_pending_payment_blocked(mocker):
    """Test that user with pending payment is blocked from booking."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Create pending payment
    baker.make(
        Payment,
        user=user,
        status=Payment.PaymentStatus.PENDING,
        payment_type=Payment.PaymentType.FINAL,
    )

    future_time = timezone.now() + timedelta(days=1)
    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=future_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc._validate_appointment_rules()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-004"


@pytest.mark.django_db
def test_appointment_service_user_with_paid_appointment_blocked(mocker):
    """Test that user with PAID appointment (not yet confirmed) is blocked."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Create appointment in CONFIRMED status with outstanding balance
    appt = baker.make(
        Appointment,
        user=user,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, hours=1),
        price_at_purchase=100000,
    )
    # Create partial payment to simulate outstanding balance
    baker.make(
        'finances.Payment',
        appointment=appt,
        user=user,
        amount=50000,  # Only half paid
        status='APPROVED',
        payment_type='ADVANCE'
    )

    future_time = timezone.now() + timedelta(days=2)
    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=future_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc._validate_appointment_rules()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-004"


@pytest.mark.django_db
def test_appointment_service_client_active_limit_exceeded(mocker):
    """Test that regular CLIENT role cannot exceed 1 active appointment."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Create 1 active appointment (CLIENT limit is 1)
    baker.make(
        Appointment,
        user=user,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, hours=1),
    )

    future_time = timezone.now() + timedelta(days=2)
    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=future_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc._validate_appointment_rules()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-003"


@pytest.mark.django_db
def test_appointment_service_staff_not_available_in_time(mocker):
    """Test that booking fails when staff is not available at requested time."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Staff available only 9-12, but we try to book at 14:00
    local_tz = timezone.get_current_timezone()
    future_time = timezone.now() + timedelta(days=1)
    day_of_week = future_time.astimezone(local_tz).isoweekday()

    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("12:00", "%H:%M").time(),
    )

    # Try to book at 14:00
    start_time = future_time.astimezone(local_tz).replace(hour=14, minute=0, second=0, microsecond=0)

    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=start_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc._ensure_staff_is_available()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-002"


@pytest.mark.django_db
def test_appointment_service_staff_has_exclusion(mocker):
    """Test that booking fails when staff has an exclusion at requested time."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    local_tz = timezone.get_current_timezone()
    future_time = timezone.now() + timedelta(days=1)
    day_of_week = future_time.astimezone(local_tz).isoweekday()

    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    # Add exclusion at 10:00-11:00
    start_time = future_time.astimezone(local_tz).replace(hour=10, minute=0, second=0, microsecond=0)
    baker.make(
        AvailabilityExclusion,
        staff_member=staff,
        date=start_time.date(),
        start_time=timezone.datetime.strptime("10:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("11:00", "%H:%M").time(),
    )

    svc = AppointmentService(user=user, services=[service], staff_member=staff, start_time=start_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc._ensure_staff_is_available()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-002"


@pytest.mark.django_db
def test_appointment_service_duplicate_service_raises(mocker):
    """Test that duplicate services in the same appointment raise error."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    user = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    local_tz = timezone.get_current_timezone()
    future_time = timezone.now() + timedelta(days=1)
    day_of_week = future_time.astimezone(local_tz).isoweekday()

    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    start_time = future_time.astimezone(local_tz).replace(hour=10, minute=0, second=0, microsecond=0)

    mocker.patch("spa.services.appointments.PaymentService.create_advance_payment_for_appointment", return_value=None)
    mocker.patch("core.caching.acquire_lock", return_value=True)

    # Pass the same service twice
    svc = AppointmentService(user=user, services=[service, service], staff_member=staff, start_time=start_time)

    with pytest.raises(BusinessLogicError) as exc_info:
        svc.create_appointment_with_lock()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "APP-005"

    cache.clear()


# ============================================================
# Tests for low supervision capacity
# ============================================================

@pytest.mark.django_db
def test_low_supervision_capacity_enforced(mocker):
    """Test that low supervision appointments respect capacity limits."""
    category = baker.make(ServiceCategory, is_low_supervision=True)
    service = baker.make(Service, category=category, duration=60)
    user1 = baker.make(CustomUser, role=CustomUser.Role.CLIENT)
    user2 = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Set low supervision capacity to 1
    settings = GlobalSettings.load()
    settings.low_supervision_capacity = 1
    settings.save()

    local_tz = timezone.get_current_timezone()
    future_time = timezone.now() + timedelta(days=1)
    start_time = future_time.astimezone(local_tz).replace(hour=10, minute=0, second=0, microsecond=0)

    mocker.patch("spa.services.appointments.PaymentService.create_advance_payment_for_appointment", return_value=None)
    mocker.patch("core.caching.acquire_lock", return_value=True)

    # First appointment should succeed
    svc1 = AppointmentService(user=user1, services=[service], staff_member=None, start_time=start_time)
    appt1 = svc1.create_appointment_with_lock()
    assert appt1 is not None

    # Second appointment at same time should fail due to capacity
    svc2 = AppointmentService(user=user2, services=[service], staff_member=None, start_time=start_time)
    with pytest.raises(BusinessLogicError) as exc_info:
        svc2.create_appointment_with_lock()

    error_code = exc_info.value.detail.get('code') if isinstance(exc_info.value.detail, dict) else None
    assert error_code == "SRV-003"

    cache.clear()


# ============================================================
# Tests for reschedule_appointment
# ============================================================

@pytest.mark.django_db
def test_reschedule_appointment_within_24hrs_as_client_fails():
    """Test that clients cannot reschedule within 24 hours of appointment."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Appointment starting in 12 hours
    near_future = timezone.now() + timedelta(hours=12)
    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=near_future,
        end_time=near_future + timedelta(hours=1),
        reschedule_count=0,
    )

    new_start_time = timezone.now() + timedelta(days=2)

    with pytest.raises(ValidationError, match="Solo puedes reagendar hasta dos veces"):
        AppointmentService.reschedule_appointment(appointment, new_start_time, client)


@pytest.mark.django_db
def test_reschedule_appointment_exceed_limit_as_client_fails():
    """Test that clients cannot reschedule more than 2 times."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Appointment far in future but already rescheduled 2 times
    far_future = timezone.now() + timedelta(days=10)
    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=far_future,
        end_time=far_future + timedelta(hours=1),
        reschedule_count=2,
    )

    new_start_time = timezone.now() + timedelta(days=15)

    with pytest.raises(ValidationError, match="Solo puedes reagendar hasta dos veces"):
        AppointmentService.reschedule_appointment(appointment, new_start_time, client)


@pytest.mark.django_db
def test_reschedule_appointment_as_staff_bypasses_restrictions():
    """Test that staff can reschedule even with restrictions."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    # Appointment in 12 hours and already rescheduled 2 times
    near_future = timezone.now() + timedelta(hours=12)
    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=near_future,
        end_time=near_future + timedelta(hours=1),
        reschedule_count=2,
    )

    new_start_time = timezone.now() + timedelta(days=2)

    # Staff should be able to reschedule
    rescheduled = AppointmentService.reschedule_appointment(appointment, new_start_time, staff)

    assert rescheduled.start_time == new_start_time
    assert rescheduled.reschedule_count == 3
    assert rescheduled.status == Appointment.AppointmentStatus.RESCHEDULED

    # Verify audit log was created
    audit_log = AuditLog.objects.filter(
        action=AuditLog.Action.APPOINTMENT_RESCHEDULE_FORCE,
        target_appointment=appointment
    ).first()
    assert audit_log is not None


@pytest.mark.django_db
def test_reschedule_appointment_client_cannot_modify_others():
    """Test that clients cannot reschedule other users' appointments."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client1 = baker.make(CustomUser, role=CustomUser.Role.CLIENT)
    client2 = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    far_future = timezone.now() + timedelta(days=10)
    appointment = baker.make(
        Appointment,
        user=client1,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=far_future,
        end_time=far_future + timedelta(hours=1),
        reschedule_count=0,
    )

    new_start_time = timezone.now() + timedelta(days=15)

    with pytest.raises(ValidationError, match="No puedes modificar citas de otros usuarios"):
        AppointmentService.reschedule_appointment(appointment, new_start_time, client2)


@pytest.mark.django_db
def test_reschedule_appointment_past_time_fails():
    """Test that rescheduling to past time fails."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    far_future = timezone.now() + timedelta(days=10)
    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=far_future,
        end_time=far_future + timedelta(hours=1),
        reschedule_count=0,
    )

    past_time = timezone.now() - timedelta(hours=1)

    with pytest.raises(ValidationError, match="debe estar en el futuro"):
        AppointmentService.reschedule_appointment(appointment, past_time, staff)


@pytest.mark.django_db
def test_reschedule_appointment_conflict_fails():
    """Test that rescheduling to conflicting slot fails."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    far_future = timezone.now() + timedelta(days=10)

    # Existing appointment
    appointment1 = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=far_future,
        end_time=far_future + timedelta(hours=1),
        reschedule_count=0,
    )

    # Another appointment blocking the target slot
    target_time = timezone.now() + timedelta(days=15)
    baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=target_time,
        end_time=target_time + timedelta(hours=1),
    )

    # Try to reschedule to the blocked slot
    with pytest.raises(ValidationError, match="ya no está disponible"):
        AppointmentService.reschedule_appointment(appointment1, target_time, staff)


# ============================================================
# Tests for complete_appointment
# ============================================================

@pytest.mark.django_db
def test_complete_appointment_as_client_fails():
    """Test that clients cannot complete appointments."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=timezone.now() - timedelta(hours=1),
        end_time=timezone.now(),
    )

    with pytest.raises(ValidationError, match="No tienes permisos para completar"):
        AppointmentService.complete_appointment(appointment, client)


@pytest.mark.django_db
def test_complete_appointment_with_outstanding_balance_fails(mocker):
    """Test that appointments with outstanding balance cannot be completed."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff_user = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff_user,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=timezone.now() - timedelta(hours=1),
        end_time=timezone.now(),
    )

    # Mock outstanding balance
    mocker.patch("spa.services.appointments.PaymentService.calculate_outstanding_amount", return_value=Decimal('50.00'))

    with pytest.raises(ValidationError, match="saldo final pendiente"):
        AppointmentService.complete_appointment(appointment, staff_user)


@pytest.mark.django_db
def test_complete_appointment_success(mocker):
    """Test successful appointment completion by staff."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60)
    staff_user = baker.make(CustomUser, role=CustomUser.Role.STAFF, phone_number="+1234567890")
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff_user,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=timezone.now() - timedelta(hours=1),
        end_time=timezone.now(),
    )

    # Mock no outstanding balance
    mocker.patch("spa.services.appointments.PaymentService.calculate_outstanding_amount", return_value=Decimal('0'))
    mocker.patch("spa.services.appointments.PaymentService.reset_user_cancellation_history")

    completed = AppointmentService.complete_appointment(appointment, staff_user)

    assert completed.status == Appointment.AppointmentStatus.COMPLETED
    assert completed.outcome == Appointment.AppointmentOutcome.NONE

    # Verify audit log
    audit_log = AuditLog.objects.filter(
        action=AuditLog.Action.APPOINTMENT_COMPLETED,
        target_appointment=appointment
    ).first()
    assert audit_log is not None


# ============================================================
# Tests for build_ical_event
# ============================================================

@pytest.mark.django_db
def test_build_ical_event():
    """Test that iCal event is properly formatted."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60, name="Massage")
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    client = baker.make(CustomUser, role=CustomUser.Role.CLIENT)

    start_time = timezone.now() + timedelta(days=1)
    appointment = baker.make(
        Appointment,
        user=client,
        staff_member=staff,
        status=Appointment.AppointmentStatus.CONFIRMED,
        start_time=start_time,
        end_time=start_time + timedelta(hours=1),
    )

    ical = AppointmentService.build_ical_event(appointment)

    assert "BEGIN:VCALENDAR" in ical
    assert "BEGIN:VEVENT" in ical
    assert f"UID:{appointment.id}@studiozens" in ical
    assert "LOCATION:StudioZens" in ical
    assert "END:VEVENT" in ical
    assert "END:VCALENDAR" in ical


# ============================================================
# Tests for VIP pricing
# ============================================================

@pytest.mark.django_db
def test_appointment_service_vip_pricing(mocker):
    """Test that VIP users get VIP pricing on appointments."""
    category = baker.make(ServiceCategory, is_low_supervision=False)
    service = baker.make(Service, category=category, duration=60, price=Decimal('100.00'), vip_price=Decimal('75.00'))
    staff = baker.make(CustomUser, role=CustomUser.Role.STAFF)
    vip_user = baker.make(CustomUser, role=CustomUser.Role.VIP)

    local_tz = timezone.get_current_timezone()
    future_time = timezone.now() + timedelta(days=1)
    day_of_week = future_time.astimezone(local_tz).isoweekday()

    StaffAvailability.objects.filter(staff_member=staff).delete()
    baker.make(
        StaffAvailability,
        staff_member=staff,
        day_of_week=day_of_week,
        start_time=timezone.datetime.strptime("09:00", "%H:%M").time(),
        end_time=timezone.datetime.strptime("17:00", "%H:%M").time(),
    )

    start_time = future_time.astimezone(local_tz).replace(hour=10, minute=0, second=0, microsecond=0)

    mocker.patch("spa.services.appointments.PaymentService.create_advance_payment_for_appointment", return_value=None)
    mocker.patch("core.caching.acquire_lock", return_value=True)

    svc = AppointmentService(user=vip_user, services=[service], staff_member=staff, start_time=start_time)
    appt = svc.create_appointment_with_lock()

    assert appt.price_at_purchase == Decimal('75.00')

    cache.clear()
